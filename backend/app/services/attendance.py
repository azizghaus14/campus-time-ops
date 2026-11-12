"""Attendance Risk (read-only): forecast each student's attendance against ATTENDANCE_THRESHOLD using their intake
group's REAL timetable. Applies to all students. Takes no actions. All students are synthetic.

Term calendar per group (DECISIONS D-09):
  - inside the published feed window: the REAL sessions (after any executed re-plans)
  - before the window: weekly recurrence of each (module, weekday, start) pattern back to the module start date
    (CLASS_CODE suffix), skipping holidays/weekends
  - after the window: weekly recurrence forward to TERM_END, skipping holidays
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from fractions import Fraction
from functools import lru_cache
from typing import Optional

from ..config import MYT, settings
from ..data.loader import Dataset, get_dataset
from ..domain import Group, hhmm
from .errors import NotFound, ToolError
from .holidays import holiday_on
from .policy import cite

STUDENTS_FILE = "synthetic/students.json"


# ------------------------------------------------------------------ calendar
def _is_teaching_day(d: date) -> bool:
    return d.weekday() < 5 and holiday_on(d) is None


def occ_key(module: str, d: date, start: int) -> str:
    return f"{module}|{d.isoformat()}|{start}"


def group_occurrences(group: Group, term_end: Optional[date] = None) -> list[dict]:
    ds = get_dataset()
    term_end = term_end or date.fromisoformat(settings.term_end)
    cache = ds.__dict__.setdefault("_occ_cache", {})
    ck = (group, term_end)
    if ck not in cache:
        cache[ck] = _group_occurrences(ds, group, term_end)
    return cache[ck]


def _group_occurrences(ds: Dataset, group: Group, term_end: date) -> list[dict]:
    win_start, win_end = ds.dates[0], ds.dates[-1]
    occ: dict[str, dict] = {}
    patterns: dict[tuple, dict] = {}
    for s in (ds.sessions[i] for i in ds.by_group.get(group, [])):
        k = occ_key(s.module_name, s.date, s.start_min)
        occ[k] = {"key": k, "module": s.module_name, "date": s.date, "start": s.start_min, "end": s.end_min,
                  "room": s.room, "lecturer_id": s.lecturer_id, "session_id": s.id, "source": "feed"}
        base_d = s.orig_date or s.date
        base_s = s.orig_start_min if s.orig_start_min is not None else s.start_min
        try:
            mod_start = date.fromisoformat(s.class_codes[0].split("___")[-1])
        except Exception:
            mod_start = None
        p = patterns.setdefault((s.module_name, base_d.weekday(), base_s, s.duration),
                                {"first": base_d, "last": base_d, "mod_start": mod_start, "room": s.orig_room or s.room, "lect": s.lecturer_id})
        p["first"], p["last"] = min(p["first"], base_d), max(p["last"], base_d)
        if mod_start and (p["mod_start"] is None or mod_start < p["mod_start"]):
            p["mod_start"] = mod_start
    for (module, _wd, start, dur), p in patterns.items():
        lo = p["mod_start"] or (win_start - timedelta(weeks=6))
        d = p["first"] - timedelta(weeks=1)
        while d >= lo:
            if d < win_start and _is_teaching_day(d):
                k = occ_key(module, d, start)
                occ.setdefault(k, {"key": k, "module": module, "date": d, "start": start, "end": start + dur, "room": p["room"],
                                   "lecturer_id": p["lect"], "session_id": None, "source": "projected-past"})
            d -= timedelta(weeks=1)
        d = p["last"] + timedelta(weeks=1)
        while d <= term_end:
            if d > win_end and _is_teaching_day(d):
                k = occ_key(module, d, start)
                occ.setdefault(k, {"key": k, "module": module, "date": d, "start": start, "end": start + dur, "room": p["room"],
                                   "lecturer_id": p["lect"], "session_id": None, "source": "projected-future"})
            d += timedelta(weeks=1)
    return sorted(occ.values(), key=lambda o: (o["date"], o["start"], o["module"]))


def is_past(o: dict, now: datetime) -> bool:
    return datetime(o["date"].year, o["date"].month, o["date"].day, o["end"] // 60, o["end"] % 60, tzinfo=MYT) <= now


# ------------------------------------------------------------------ students
@lru_cache(maxsize=1)
def _students() -> dict[str, dict]:
    p = settings.data_dir / STUDENTS_FILE
    if not p.exists():
        raise ToolError("NO_SYNTHETIC_DATA", "data/synthetic/students.json missing - run `make data`")
    return {s["id"]: s for s in json.loads(p.read_text())["students"]}


def reload_students() -> None:
    _students.cache_clear()


def get_student_record(student_id: str) -> dict:
    s = _students().get(student_id)
    if not s:
        raise NotFound("UNKNOWN_STUDENT", f"No student {student_id}")
    return s


def _absent(st: dict) -> set[str]:
    return set(st["attendance_records"]["absent"])


def list_students(intake: Optional[str] = None, q: Optional[str] = None, limit: int = 200) -> dict:
    out = []
    for s in _students().values():
        if intake and s["intake"] != intake.upper():
            continue
        if q and q.lower() not in (s["name"] + s["id"] + s["intake"]).lower():
            continue
        out.append({k: s[k] for k in ("id", "name", "intake", "grouping")})
    return {"count": len(out), "students": out[:limit]}


def get_attendance(student_id: str) -> dict:
    st = get_student_record(student_id)
    now = settings.now()
    absent = _absent(st)
    recs = [{"key": o["key"], "module": o["module"], "date": o["date"].isoformat(), "time": f"{hhmm(o['start'])}-{hhmm(o['end'])}",
             "status": "ABSENT" if o["key"] in absent else "PRESENT", "source": o["source"]}
            for o in group_occurrences((st["intake"], st["grouping"])) if is_past(o, now)]
    by_mod = defaultdict(lambda: [0, 0])
    for r in recs:
        by_mod[r["module"]][1] += 1
        by_mod[r["module"]][0] += r["status"] == "PRESENT"
    attended = sum(1 for r in recs if r["status"] == "PRESENT")
    return {
        "student_id": student_id, "name": st["name"], "intake": st["intake"], "grouping": st["grouping"],
        "sessions_so_far": len(recs), "attended": attended, "percent": round(100 * attended / len(recs), 1) if recs else None,
        "by_module": [{"module": m, "attended": a, "held": n, "percent": round(100 * a / n, 1)} for m, (a, n) in sorted(by_mod.items())],
        "records": recs,
    }


def max_more_absences(attended: int, held: int, remaining: int, threshold: float) -> int:
    """Largest k (0..remaining) such that (attended + remaining - k) / (held + remaining) >= threshold.
    Exact rational arithmetic; returns -1 if the threshold can't be reached even with full attendance."""
    k = Fraction(attended + remaining) - Fraction(str(threshold)) * (held + remaining)
    return -1 if k < 0 else min(remaining, math.floor(k))


def attendance_forecast(student_id: str) -> dict:
    st = get_student_record(student_id)
    thr = settings.attendance_threshold
    now = settings.now()
    absent = _absent(st)
    occs = group_occurrences((st["intake"], st["grouping"]))
    past = [o for o in occs if is_past(o, now)]
    future = [o for o in occs if not is_past(o, now)]
    recent_cut = now.date() - timedelta(days=28)

    mods: dict[str, dict] = defaultdict(lambda: {"held": 0, "attended": 0, "remaining": 0, "recent_held": 0, "recent_abs": 0,
                                                 "consecutive_abs": 0, "remaining_feed": 0})
    for o in past:
        m = mods[o["module"]]
        present = o["key"] not in absent
        m["held"] += 1
        m["attended"] += present
        if o["date"] >= recent_cut:
            m["recent_held"] += 1
            m["recent_abs"] += not present
        m["consecutive_abs"] = 0 if present else m["consecutive_abs"] + 1
    for o in future:
        mods[o["module"]]["remaining"] += 1
        mods[o["module"]]["remaining_feed"] += o["source"] == "feed"

    held = sum(m["held"] for m in mods.values())
    attended = sum(m["attended"] for m in mods.values())
    remaining = sum(m["remaining"] for m in mods.values())
    recent_held = sum(m["recent_held"] for m in mods.values())
    recent_abs = sum(m["recent_abs"] for m in mods.values())
    abs_rate = (recent_abs / recent_held) if recent_held else ((held - attended) / held if held else 0.0)

    per_module = []
    for name, m in sorted(mods.items()):
        total = m["held"] + m["remaining"]
        proj = (m["attended"] + m["remaining"] * (1 - abs_rate)) / total if total else None
        per_module.append({
            "module": name, "held": m["held"], "attended": m["attended"],
            "percent": round(100 * m["attended"] / m["held"], 1) if m["held"] else None,
            "remaining": m["remaining"], "remaining_in_published_timetable": m["remaining_feed"],
            "max_more_absences": max_more_absences(m["attended"], m["held"], m["remaining"], thr),
            "projected_percent_end": round(100 * proj, 1) if proj is not None else None,
            "consecutive_absences": m["consecutive_abs"],
        })
    binding = min(per_module, key=lambda p: (p["max_more_absences"], p["remaining"]), default=None)
    overall_mma = max_more_absences(attended, held, remaining, thr)
    mma = binding["max_more_absences"] if binding else overall_mma

    breach = None
    run = {k: [v["attended"], v["held"]] for k, v in mods.items()}
    for o in future:
        r = run[o["module"]]
        r[0] += 1 - abs_rate
        r[1] += 1
        if r[0] / r[1] < thr:
            breach = {"date": o["date"].isoformat(), "module": o["module"]}
            break

    weekly = []
    if past:
        d0 = past[0]["date"]
        wk = defaultdict(lambda: [0, 0])
        for o in past:
            w = (o["date"] - d0).days // 7
            wk[w][1] += 1
            wk[w][0] += o["key"] not in absent
        ca = cn = 0
        for w in sorted(wk):
            ca, cn = ca + wk[w][0], cn + wk[w][1]
            weekly.append({"week": w + 1, "week_start": (d0 + timedelta(weeks=w)).isoformat(),
                           "week_percent": round(100 * wk[w][0] / wk[w][1], 1), "cumulative_percent": round(100 * ca / cn, 1)})
    proj_overall = (attended + remaining * (1 - abs_rate)) / (held + remaining) if (held + remaining) else None
    nxt = next((o for o in future if o["source"] == "feed"), future[0] if future else None)
    pct = round(100 * attended / held, 1) if held else None
    if len(weekly) >= 3 and weekly[-1]["week_percent"] < weekly[-3]["week_percent"] - 5:
        trend = "declining"
    elif len(weekly) >= 3 and weekly[-1]["week_percent"] > weekly[-3]["week_percent"] + 5:
        trend = "improving"
    else:
        trend = "steady"

    if pct is None:
        msg = f"No sessions have been recorded yet this term. Your intake has {remaining} sessions left."
    elif binding and binding["max_more_absences"] < 0 and binding["percent"] is not None:
        msg = (f"You're at {pct:.0f}% overall. In {binding['module']} you are at {binding['percent']:.0f}% and can no longer reach "
               f"{thr:.0%} this term even with full attendance - please talk to your programme leader; support is available.")
    else:
        scope = f"in {binding['module']}" if binding and len(per_module) > 1 else "overall"
        msg = (f"You're at {pct:.0f}%. Your intake has {remaining} sessions left this term. If you miss more than {mma} ({scope}), "
               f"you'll fall below the {thr:.0%} attendance requirement."
               + (f" Your next class is {nxt['date'].strftime('%a')} {hhmm(nxt['start'])}, {nxt['room']}." if nxt else ""))
    return {
        "student_id": student_id, "name": st["name"], "intake": st["intake"], "grouping": st["grouping"], "threshold": thr,
        "current_percent": pct, "held": held, "attended": attended, "remaining_sessions": remaining,
        "remaining_in_published_timetable": sum(m["remaining_feed"] for m in mods.values()),
        "max_more_absences": mma, "max_more_absences_overall": overall_mma, "binding_module": binding["module"] if binding else None,
        "projected_percent_end": round(100 * proj_overall, 1) if proj_overall is not None else None,
        "recent_absence_rate": round(abs_rate, 3), "trend": trend, "weekly": weekly, "projected_breach": breach,
        "per_module": per_module, "max_consecutive_absences": max((m["consecutive_abs"] for m in mods.values()), default=0),
        "next_class": {"date": nxt["date"].isoformat(), "time": f"{hhmm(nxt['start'])}-{hhmm(nxt['end'])}", "room": nxt["room"], "module": nxt["module"]} if nxt else None,
        "message": msg,
        "method": f"per module (HB §2.2: 80% for each module); remaining = real published sessions + weekly recurrence to TERM_END {settings.term_end}",
        "citations": cite(["R-ATT-80", "R-ATT-THRESHOLD", "R-ATT-EXAM"]),
    }


def _risk(f: dict) -> tuple[int, list[str]]:
    thr = f["threshold"] * 100
    cur = f["current_percent"] if f["current_percent"] is not None else 100
    score, reasons = 0, []
    if f["max_more_absences"] < 0:
        score += 100
        reasons.append(f"cannot reach {thr:.0f}% in {f['binding_module']}")
    else:
        bm = next((m for m in f["per_module"] if m["module"] == f["binding_module"]), None)
        slipping = bm is not None and bm["percent"] is not None and bm["percent"] < 90
        if slipping and f["max_more_absences"] <= 2:
            score += {0: 50, 1: 35, 2: 20}[f["max_more_absences"]]
            reasons.append(f"only {f['max_more_absences']} more absence(s) allowed in {f['binding_module']} ({bm['percent']:.0f}% so far)")
    if cur < thr:
        score += 40
        reasons.append(f"currently {cur}% < {thr:.0f}%")
    elif cur < thr + 3:
        score += 15
        reasons.append(f"currently {cur}%, within 3 pts of {thr:.0f}%")
    if f["projected_percent_end"] is not None and f["projected_percent_end"] < thr:
        score += 25
        reasons.append(f"projected {f['projected_percent_end']}% at term end")
    if f["max_consecutive_absences"] >= 3:
        score += 20
        reasons.append(f"{f['max_consecutive_absences']} consecutive absences (R-ATT-4C)")
    if f["trend"] == "declining":
        score += 10
        reasons.append("declining trend")
    return score, reasons


def attendance_risk_list(date_str: Optional[str] = None, limit: int = 100, min_score: int = 30) -> dict:
    """Ranked, read-only list of students below or heading towards the threshold."""
    t0 = datetime.now()
    rows, below = [], 0
    for st in _students().values():
        f = attendance_forecast(st["id"])
        if f["current_percent"] is not None and f["current_percent"] < f["threshold"] * 100:
            below += 1
        score, reasons = _risk(f)
        if score < min_score:
            continue
        rows.append({
            "student_id": st["id"], "name": st["name"], "intake": st["intake"], "grouping": st["grouping"],
            "current_percent": f["current_percent"], "projected_percent_end": f["projected_percent_end"],
            "max_more_absences": f["max_more_absences"], "binding_module": f["binding_module"],
            "remaining_sessions": f["remaining_sessions"], "trend": f["trend"], "risk_score": score, "reasons": reasons,
            "weekly": [w["cumulative_percent"] for w in f["weekly"]],
        })
    rows.sort(key=lambda r: (-r["risk_score"], r["student_id"]))
    return {
        "date": date_str or settings.now().date().isoformat(), "students_total": len(_students()), "at_risk": len(rows),
        "below_threshold": below, "threshold": settings.attendance_threshold, "students": rows[:limit],
        "elapsed_s": round((datetime.now() - t0).total_seconds(), 2),
        "citations": cite(["R-ATT-80", "R-ATT-THRESHOLD", "R-ATT-4C"]),
    }
