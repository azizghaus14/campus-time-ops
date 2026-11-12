"""Visa Guardian: attendance forecast against the student-pass requirement using each intake group's REAL timetable,
risk sweep, and a human-approved escalation ladder (R-ESC-1..4). All students are synthetic.

Term calendar per group (documented assumption, DECISIONS D-09):
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
from ..domain import Group, ProposalKind, ProposalStatus, hhmm, iso
from .audit import log_event
from .errors import Conflict, NotFound, ToolError, require
from .holidays import holiday_on
from .policy import cite
from .store import get_store
from .workspace import CalendarEvent, Draft, addr_lecturer, addr_role, get_workspace, new_uid

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
    real = [ds.sessions[i] for i in ds.by_group.get(group, [])]
    occ: dict[str, dict] = {}
    patterns: dict[tuple, dict] = {}
    for s in real:
        k = occ_key(s.module_name, s.date, s.start_min)
        occ[k] = {"key": k, "module": s.module_name, "date": s.date, "start": s.start_min, "end": s.end_min,
                  "room": s.room, "lecturer_id": s.lecturer_id, "session_id": s.id, "source": "feed"}
        base_d, base_s = (s.orig_date or s.date), (s.orig_start_min if s.orig_start_min is not None else s.start_min)
        pk = (s.module_name, base_d.weekday(), base_s, s.duration)
        mod_start = None
        try:
            mod_start = date.fromisoformat(s.class_codes[0].split("___")[-1])
        except Exception:
            pass
        p = patterns.setdefault(pk, {"first": base_d, "last": base_d, "mod_start": mod_start, "room": s.orig_room or s.room, "lect": s.lecturer_id})
        p["first"] = min(p["first"], base_d)
        p["last"] = max(p["last"], base_d)
        if mod_start and (p["mod_start"] is None or mod_start < p["mod_start"]):
            p["mod_start"] = mod_start
    for (module, wd, start, dur), p in patterns.items():
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


def _is_past(o: dict, now: datetime) -> bool:
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


def list_students(international_only: bool = False, intake: Optional[str] = None, q: Optional[str] = None, limit: int = 200) -> dict:
    out = []
    for s in _students().values():
        if international_only and not s["is_international"]:
            continue
        if intake and s["intake"] != intake.upper():
            continue
        if q and q.lower() not in (s["name"] + s["id"] + s["intake"]).lower():
            continue
        out.append({k: s[k] for k in ("id", "name", "intake", "grouping", "nationality", "is_international", "pass_expiry", "profile", "demo")
                    if k in s})
    return {"count": len(out), "students": out[:limit]}


def get_attendance(student_id: str) -> dict:
    st = get_student_record(student_id)
    now = settings.now()
    absent = set(st.get("absences", []))
    recs = []
    for o in group_occurrences((st["intake"], st["grouping"])):
        if _is_past(o, now):
            recs.append({"key": o["key"], "module": o["module"], "date": o["date"].isoformat(), "time": f"{hhmm(o['start'])}-{hhmm(o['end'])}",
                         "status": "ABSENT" if o["key"] in absent else "PRESENT", "source": o["source"]})
    by_mod = defaultdict(lambda: [0, 0])
    for r in recs:
        by_mod[r["module"]][1] += 1
        by_mod[r["module"]][0] += r["status"] == "PRESENT"
    total = len(recs)
    attended = sum(1 for r in recs if r["status"] == "PRESENT")
    return {
        "student_id": student_id, "name": st["name"], "intake": st["intake"], "grouping": st["grouping"],
        "sessions_so_far": total, "attended": attended, "percent": round(100 * attended / total, 1) if total else None,
        "by_module": [{"module": m, "attended": a, "held": n, "percent": round(100 * a / n, 1)} for m, (a, n) in sorted(by_mod.items())],
        "records": recs,
    }


def max_more_absences(attended: int, held: int, remaining: int, threshold: float) -> int:
    """Largest k (0..remaining) such that (attended + remaining - k) / (held + remaining) >= threshold.
    Exact rational arithmetic; returns -1 if the threshold can't be reached even with full attendance."""
    thr = Fraction(str(threshold))
    k = Fraction(attended + remaining) - thr * (held + remaining)
    if k < 0:
        return -1
    return min(remaining, math.floor(k))


def attendance_forecast(student_id: str) -> dict:
    st = get_student_record(student_id)
    thr = settings.attendance_threshold
    now = settings.now()
    absent = set(st.get("absences", []))
    occs = group_occurrences((st["intake"], st["grouping"]))
    past = [o for o in occs if _is_past(o, now)]
    future = [o for o in occs if not _is_past(o, now)]
    recent_cut = now.date() - timedelta(days=28)

    mods: dict[str, dict] = defaultdict(lambda: {"held": 0, "attended": 0, "remaining": 0, "recent_held": 0, "recent_abs": 0,
                                                 "consecutive_abs": 0, "remaining_feed": 0})
    for o in past:
        m = mods[o["module"]]
        m["held"] += 1
        a = o["key"] not in absent
        m["attended"] += a
        if o["date"] >= recent_cut:
            m["recent_held"] += 1
            m["recent_abs"] += not a
        m["consecutive_abs"] = 0 if a else m["consecutive_abs"] + 1
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
        mma = max_more_absences(m["attended"], m["held"], m["remaining"], thr)
        proj = (m["attended"] + m["remaining"] * (1 - abs_rate)) / (m["held"] + m["remaining"]) if (m["held"] + m["remaining"]) else None
        per_module.append({
            "module": name, "held": m["held"], "attended": m["attended"],
            "percent": round(100 * m["attended"] / m["held"], 1) if m["held"] else None,
            "remaining": m["remaining"], "remaining_in_published_timetable": m["remaining_feed"],
            "max_more_absences": mma, "projected_percent_end": round(100 * proj, 1) if proj is not None else None,
            "consecutive_absences": m["consecutive_abs"],
        })
    binding = min((p for p in per_module if p["remaining"] or p["held"]), key=lambda p: (p["max_more_absences"], p["remaining"]), default=None)
    overall_mma = max_more_absences(attended, held, remaining, thr)
    mma = binding["max_more_absences"] if binding else overall_mma

    # projected breach date: walk future sessions applying the recent absence rate (expected value)
    breach = None
    run = {k: [v["attended"], v["held"]] for k, v in mods.items()}
    for o in future:
        r = run[o["module"]]
        r[0] += 1 - abs_rate
        r[1] += 1
        if r[1] and r[0] / r[1] < thr:
            breach = {"date": o["date"].isoformat(), "module": o["module"]}
            break

    trend = []
    if past:
        d0 = past[0]["date"]
        wk = defaultdict(lambda: [0, 0])
        for o in past:
            w = (o["date"] - d0).days // 7
            wk[w][1] += 1
            wk[w][0] += o["key"] not in absent
        cum_a = cum_n = 0
        for w in sorted(wk):
            cum_a += wk[w][0]
            cum_n += wk[w][1]
            trend.append({"week": w + 1, "week_start": (d0 + timedelta(weeks=w)).isoformat(), "week_percent": round(100 * wk[w][0] / wk[w][1], 1),
                          "cumulative_percent": round(100 * cum_a / cum_n, 1)})
    proj_overall = (attended + remaining * (1 - abs_rate)) / (held + remaining) if (held + remaining) else None
    nxt = next((o for o in future if o["source"] == "feed"), future[0] if future else None)
    pct = round(100 * attended / held, 1) if held else None
    direction = "declining" if len(trend) >= 3 and trend[-1]["week_percent"] < trend[-3]["week_percent"] - 5 else ("improving" if len(trend) >= 3 and trend[-1]["week_percent"] > trend[-3]["week_percent"] + 5 else "steady")

    if pct is None:
        msg = (f"No sessions have been recorded for you yet this term. Your intake has {remaining} sessions left; "
               f"you can miss at most {max(0, overall_mma)} and stay above {thr:.0%}.")
    elif binding and binding["max_more_absences"] < 0 and binding["percent"] is not None:
        msg = (f"You're at {pct:.0f}% overall. In {binding['module']} you are at {binding['percent']:.0f}% and can no longer reach "
               f"{thr:.0%} this term even with full attendance - please talk to your advisor this week; there is support available.")
    else:
        msg = (f"You're at {pct:.0f}%. Your intake has {remaining} sessions left this term. "
               + (f"If you miss more than {mma} ({'in ' + binding['module'] if binding and len(per_module) > 1 else 'overall'}), you'll fall below the "
                  f"{thr:.0%} student-pass requirement." if binding else "")
               + (f" Your next class is {nxt['date'].strftime('%a')} {hhmm(nxt['start'])}, {nxt['room']}." if nxt else ""))
    return {
        "student_id": student_id, "name": st["name"], "intake": st["intake"], "grouping": st["grouping"],
        "is_international": st["is_international"], "threshold": thr,
        "current_percent": pct, "held": held, "attended": attended,
        "remaining_sessions": remaining,
        "remaining_in_published_timetable": sum(m["remaining_feed"] for m in mods.values()),
        "max_more_absences": mma, "max_more_absences_overall": overall_mma,
        "binding_module": binding["module"] if binding else None,
        "projected_percent_end": round(100 * proj_overall, 1) if proj_overall is not None else None,
        "recent_absence_rate": round(abs_rate, 3), "trend": direction, "weekly": trend,
        "projected_breach": breach, "per_module": per_module,
        "max_consecutive_absences": max((m["consecutive_abs"] for m in mods.values()), default=0),
        "next_class": {"date": nxt["date"].isoformat(), "time": f"{hhmm(nxt['start'])}-{hhmm(nxt['end'])}", "room": nxt["room"], "module": nxt["module"]} if nxt else None,
        "pass_expiry": st.get("pass_expiry"), "passport_expiry": st.get("passport_expiry"),
        "message": msg,
        "method": "per-module (HB §2.2: 80% for each module); remaining = real published sessions + weekly recurrence to TERM_END " + settings.term_end,
        "citations": cite(["R-ATT-80", "R-VISA-ATT", "R-ATT-EXAM"]),
    }


# ------------------------------------------------------------------ sweep + escalation
LADDER = ["R-ESC-1", "R-ESC-2", "R-ESC-3", "R-ESC-4"]
STEP_NAME = {"R-ESC-1": "Supportive nudge email", "R-ESC-2": "Advisor meeting", "R-ESC-3": "Formal attendance letter", "R-ESC-4": "International Office review"}


def _risk(f: dict, st: dict) -> tuple[int, list[str], Optional[str]]:
    thr = f["threshold"] * 100
    reasons, score = [], 0
    cur = f["current_percent"] or 100
    if f["max_more_absences"] < 0:
        score += 100
        reasons.append("cannot reach the threshold in at least one module")
    elif f["max_more_absences"] <= 3:
        score += 60 - 10 * f["max_more_absences"]
        reasons.append(f"only {f['max_more_absences']} more absence(s) allowed in {f['binding_module']}")
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
    pe, pp = st.get("passport_expiry"), st.get("pass_expiry")
    if pe and pp and pe < pp:
        score += 15
        reasons.append("passport expires before student pass (R-PASSPORT)")
    if f["trend"] == "declining":
        score += 10
        reasons.append("declining trend")
    step = None
    if score >= 20:
        if cur < thr or f["max_more_absences"] < 0:
            step = "R-ESC-3"
        elif cur < thr + 3 or f["max_consecutive_absences"] >= 3:
            step = "R-ESC-2"
        else:
            step = "R-ESC-1"
    return score, reasons, step


def _ladder_state(student_id: str) -> dict:
    return get_store().get("escalations", student_id) or {"student_id": student_id, "completed": [], "history": []}


def visa_risk_sweep(date_str: Optional[str] = None, limit: int = 100) -> dict:
    t0 = datetime.now()
    rows = []
    intl = [s for s in _students().values() if s["is_international"]]
    for st in intl:
        f = attendance_forecast(st["id"])
        score, reasons, step = _risk(f, st)
        if not step:
            continue
        ladder = _ladder_state(st["id"])
        done = ladder["completed"]
        if done:
            nxt_i = min(len(LADDER) - 1, max(LADDER.index(done[-1]) + 1, LADDER.index(step)))
            step = LADDER[nxt_i] if LADDER.index(step) <= LADDER.index(done[-1]) else step
        rows.append({
            "student_id": st["id"], "name": st["name"], "intake": st["intake"], "grouping": st["grouping"], "nationality": st["nationality"],
            "current_percent": f["current_percent"], "projected_percent_end": f["projected_percent_end"], "max_more_absences": f["max_more_absences"],
            "binding_module": f["binding_module"], "remaining_sessions": f["remaining_sessions"], "trend": f["trend"],
            "pass_expiry": st.get("pass_expiry"), "passport_expiry": st.get("passport_expiry"),
            "risk_score": score, "reasons": reasons, "proposed_step": step, "proposed_step_name": STEP_NAME[step],
            "ladder_completed": done, "weekly": [w["cumulative_percent"] for w in f["weekly"]], "demo": st.get("demo", False),
        })
    rows.sort(key=lambda r: (-r["risk_score"], r["student_id"]))
    return {
        "date": date_str or settings.now().date().isoformat(), "international_students": len(intl), "at_risk": len(rows),
        "threshold": settings.attendance_threshold, "students": rows[:limit],
        "by_step": {s: sum(1 for r in rows if r["proposed_step"] == s) for s in LADDER},
        "elapsed_s": round((datetime.now() - t0).total_seconds(), 2),
        "citations": cite(["R-VISA-ATT", "R-ATT-80", "R-ATT-4C", "R-PASSPORT", "R-ESC-1", "R-HITL"]),
    }


def plan_escalation(student_id: str, step: Optional[str] = None, created_by: str = "visa-guardian") -> dict:
    st = get_student_record(student_id)
    require(st["is_international"], "NOT_INTERNATIONAL", "Visa Guardian escalations apply to international students only")
    f = attendance_forecast(student_id)
    score, reasons, auto_step = _risk(f, st)
    ladder = _ladder_state(student_id)
    if not step:
        step = auto_step or "R-ESC-1"
        if ladder["completed"]:
            last = LADDER.index(ladder["completed"][-1])
            step = LADDER[min(len(LADDER) - 1, max(last + 1, LADDER.index(step)))]
    require(step in LADDER, "BAD_STEP", f"step must be one of {LADDER}")
    store = get_store()
    for p in store.list("proposals", kind=ProposalKind.ESCALATION.value, student_id=student_id):
        if p["status"] == ProposalStatus.DRAFT.value:
            p["status"] = ProposalStatus.SUPERSEDED.value
            store.put("proposals", p["id"], p)
    advisor = st.get("advisor_id")
    action: dict = {}
    first = st["name"].split()[0]
    thr = f"{settings.attendance_threshold:.0%}"
    if step == "R-ESC-1":
        action = {"type": "email_draft", "to": [f"{student_id.lower()}@students.{settings.workspace_demo_domain}"],
                  "cc": [addr_lecturer(advisor)] if advisor else [],
                  "subject": "Checking in on your classes",
                  "body": (f"Hi {first},\n\nI'm checking in because your attendance is at {f['current_percent']}%. "
                           f"Your intake has {f['remaining_sessions']} sessions left this term, so there is still time: if you miss no more than "
                           f"{max(0, f['max_more_absences'])} more{' of ' + f['binding_module'] if f['binding_module'] else ''}, you'll stay above the {thr} needed "
                           f"for your modules and your student pass.\n\nIf something is getting in the way - health, finances, transport, anything - "
                           f"just reply and we'll find a way to help. Student Services and your advisor are here for you.\n\n"
                           f"Your next class: {f['next_class']['module']} on {f['next_class']['date']} {f['next_class']['time']}, {f['next_class']['room']}.\n\nWarm regards,\nAcademic Advisor (demo)" if f["next_class"] else "")}
    elif step == "R-ESC-2":
        from .slots import find_common_slots

        lects = [advisor] if advisor else []
        try:
            slots = find_common_slots([{"intake": st["intake"], "grouping": st["grouping"]}], lects, 30,
                                      {"start": (settings.now().date() + timedelta(days=1)).isoformat(), "end": (settings.now().date() + timedelta(days=10)).isoformat()},
                                      {"type": "discussion", "min_capacity": 2}, top_n=3)
            opts = slots["options"]
        except ToolError:
            opts = []
        action = {"type": "advisor_meeting", "advisor_id": advisor, "slot_options": opts, "slot": opts[0] if opts else None,
                  "invite_body": (f"Hi {first}, I'd like to meet for 30 minutes to see how things are going and how we can support you "
                                  f"with attendance (currently {f['current_percent']}%). This is a supportive chat, not a disciplinary meeting.")}
    elif step == "R-ESC-3":
        action = {"type": "formal_letter_doc", "title": f"Attendance support letter - {st['name']} ({student_id})",
                  "markdown": (f"**Date:** {settings.now().date().isoformat()}\n\n**Student:** {st['name']} ({student_id}), intake {st['intake']}/{st['grouping']}\n\n"
                               f"Dear {first},\n\nOur records show your attendance is **{f['current_percent']}%**"
                               f"{', and ' + f['binding_module'] + ' is at ' + str(next(p['percent'] for p in f['per_module'] if p['module'] == f['binding_module'])) + '%' if f['binding_module'] else ''}. "
                               f"The APU Student Handbook requires a minimum of 80% attendance for each module (§2.2), and students below 80% may not sit the final "
                               f"examination (§10.2). As an international student, your student pass also depends on satisfactory attendance.\n\n"
                               f"We want to help you get back on track. Please contact your advisor within 5 working days to agree a support plan. "
                               f"If illness or other circumstances outside your control affected you, you may be eligible for an Extenuating Circumstances claim (§10.4).\n\n"
                               f"| Measure | Value |\n|---|---|\n| Current attendance | {f['current_percent']}% |\n| Sessions remaining | {f['remaining_sessions']} |\n"
                               f"| More absences allowed (binding module) | {max(0, f['max_more_absences'])} |\n| Projected at term end | {f['projected_percent_end']}% |\n\n"
                               f"Yours sincerely,\nInternational Office (demo)\n\n_Generated by Campus Time Ops; approved by a member of staff before issue._")}
    else:
        action = {"type": "io_review", "summary": f"Case review for {st['name']} ({student_id}): {', '.join(reasons)}. Ladder so far: {ladder['completed']}.",
                  "note": "No report is made to any authority without an International Office decision."}
    pid = store.next_id("PRO")
    p = {
        "id": pid, "kind": ProposalKind.ESCALATION.value, "status": ProposalStatus.DRAFT.value, "version": 1,
        "title": f"{STEP_NAME[step]} - {st['name']} ({student_id})", "student_id": student_id, "step": step,
        "created_at": settings.now().isoformat(), "created_by": created_by, "requires_approval_by": "International Office",
        "forecast": {k: f[k] for k in ("current_percent", "max_more_absences", "binding_module", "remaining_sessions", "projected_percent_end", "trend", "projected_breach")},
        "reasons": reasons, "risk_score": score, "action": action,
        "explanation": f"{STEP_NAME[step]} for {st['name']}: {', '.join(reasons) or 'requested'}. Awaiting International Office approval.",
        "citations": cite([step, "R-VISA-ATT", "R-ATT-80", "R-HITL"]), "moves": [], "unresolved": [],
        "summary": {"label": STEP_NAME[step], "student": st["name"]},
    }
    store.put("proposals", pid, p)
    log_event(created_by, "proposal.drafted", pid, after={"student": student_id, "step": step})
    return p


def execute_escalation(p: dict, who: str) -> dict:
    ws = get_workspace()
    a = p["action"]
    out: dict = {"mode": ws.mode, "actions": {}}
    if a["type"] == "email_draft":
        r = ws.create_drafts(p["id"], [Draft(to=a["to"], bcc=a.get("cc", []), subject=a["subject"], body=a["body"])])
        out["drafts"], out["actions"]["gmail_drafts"] = r, r["count"]
        out["draft_ids"] = [d["id"] for d in r["drafts"]]
    elif a["type"] == "advisor_meeting":
        require(a.get("slot"), "NO_SLOT", "No meeting slot found; re-plan with a wider window")
        s = a["slot"]
        stu = f"{p['student_id'].lower()}@students.{settings.workspace_demo_domain}"
        r = ws.create_events(p["id"], [CalendarEvent(summary=f"Advisor check-in: {p['title'].split(' - ')[-1]}", start=s["start"], end=s["end"], location=s["room"],
                                                     description=a["invite_body"], attendees=[stu] + ([addr_lecturer(a["advisor_id"])] if a.get("advisor_id") else []),
                                                     uid=new_uid(p["id"]))])
        d = ws.create_drafts(p["id"], [Draft(to=[stu], bcc=[], subject="Let's catch up - 30 min check-in", body=a["invite_body"] + f"\n\nProposed: {s['label']} in {s['room']}.")])
        out.update({"calendar": r, "drafts": d, "actions": {"calendar_events": r["count"], "gmail_drafts": d["count"]}, "draft_ids": [x["id"] for x in d["drafts"]]})
    elif a["type"] == "formal_letter_doc":
        r = ws.create_doc(p["id"], a["title"], a["markdown"])
        out["doc"], out["actions"]["docs_created"] = r, 1
    else:
        r = ws.create_doc(p["id"], f"IO case review {p['student_id']}", a["summary"] + "\n\n" + a["note"])
        out["doc"], out["actions"]["docs_created"] = r, 1
    store = get_store()
    lad = _ladder_state(p["student_id"])
    if p["step"] not in lad["completed"]:
        lad["completed"].append(p["step"])
    lad["history"].append({"step": p["step"], "proposal_id": p["id"], "approved_by": p.get("approved_by"), "at": settings.now().isoformat()})
    store.put("escalations", p["student_id"], lad)
    log_event(who, f"escalation.{p['step']}.executed", p["id"], after=out["actions"])
    return out


def daily_sweep(max_students: int = 25, who: str = "visa-guardian-workflow") -> dict:
    """The 09:00 MYT workflow: sweep -> DRAFT escalation per at-risk student -> digest draft to the International Office
    with approval links. Creates no student-facing artefact: everything waits for IO approval (R-HITL)."""
    sweep = visa_risk_sweep()
    created = []
    for r in sweep["students"][:max_students]:
        existing = [p for p in get_store().list("proposals", kind=ProposalKind.ESCALATION.value, student_id=r["student_id"]) if p["status"] == "DRAFT"]
        p = existing[0] if existing else plan_escalation(r["student_id"], created_by=who)
        created.append({"proposal_id": p["id"], "student": r["name"], "step": p["step"], "risk": r["risk_score"],
                        "approve_url": f"{settings.dashboard_base_url}/proposals/{p['id']}"})
    lines = [f"Good morning. Visa Guardian sweep for {sweep['date']}: {sweep['at_risk']} of {sweep['international_students']} international students flagged.", ""]
    lines += [f"- [{c['step']}] {c['student']} (risk {c['risk']}): approve/edit -> {c['approve_url']}" for c in created]
    lines += ["", "Nothing has been sent to students. Each item needs your approval."]
    digest = get_workspace().create_drafts(f"digest-{sweep['date']}", [Draft(to=[addr_role("international-office")], bcc=[],
                                                                                subject=f"Visa Guardian daily digest - {sweep['date']} ({len(created)} to review)", body="\n".join(lines))])
    log_event(who, "visa.daily_sweep", None, after={"at_risk": sweep["at_risk"], "drafted": len(created)})
    return {"sweep": {k: v for k, v in sweep.items() if k != "students"}, "proposals": created, "digest": digest["drafts"][0] if digest["drafts"] else None}
