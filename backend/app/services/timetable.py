"""Timetable read tools: lecturer / group / day schedules, fuzzy search, timetable health."""
from __future__ import annotations

import difflib
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any, Optional

from ..data.loader import Dataset, get_dataset
from ..domain import Session
from .errors import NotFound, ToolError, require


def parse_date(s: Any, field: str = "date") -> date:
    if isinstance(s, date):
        return s
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        raise ToolError("BAD_DATE", f"{field} must be YYYY-MM-DD", got=s)


def date_range(start: Any, end: Any) -> tuple[date, date]:
    a, b = parse_date(start, "start_date"), parse_date(end, "end_date")
    require(a <= b, "BAD_RANGE", "start_date must be <= end_date")
    require((b - a).days <= 62, "RANGE_TOO_LARGE", "max range is 62 days")
    return a, b


def sdict(ds: Dataset, s: Session) -> dict:
    d = s.to_dict()
    d["students"] = ds.session_students(s)
    room = ds.rooms.get(s.room)
    d["room_type"] = room.type if room else None
    return d


def _filter(ds: Dataset, ids: list[str], a: date, b: date) -> list[dict]:
    out = [ds.sessions[i] for i in ids if a <= ds.sessions[i].date <= b]
    out.sort(key=lambda s: (s.date, s.start_min, s.room))
    return [sdict(ds, s) for s in out]


def get_lecturer_schedule(lecturer_id: str, start_date: str, end_date: str) -> dict:
    ds = get_dataset()
    lid = (lecturer_id or "").strip().upper()
    if lid not in ds.by_lecturer:
        raise NotFound("UNKNOWN_LECTURER", f"No lecturer '{lecturer_id}'", suggestions=_lect_suggest(ds, lid))
    a, b = date_range(start_date, end_date)
    sessions = _filter(ds, ds.by_lecturer[lid], a, b)
    return {
        "lecturer_id": lid,
        "lecturer_name": ds.lecturer_names[lid],
        "count": len(sessions),
        "sessions": sessions,
    }


def get_group_schedule(intake: str, grouping: Optional[str], start_date: str, end_date: str) -> dict:
    ds = get_dataset()
    intake = (intake or "").strip().upper()
    if intake not in ds.by_intake:
        raise NotFound("UNKNOWN_INTAKE", f"No intake '{intake}'", suggestions=_intake_suggest(ds, intake))
    a, b = date_range(start_date, end_date)
    groupings = [grouping.upper()] if grouping else sorted(ds.by_intake[intake])
    ids: set[str] = set()
    for g in groupings:
        ids.update(ds.by_group.get((intake, g), []))
    sessions = _filter(ds, list(ids), a, b)
    return {"intake": intake, "groupings": groupings, "count": len(sessions), "sessions": sessions}


def get_sessions_on(date_str: str, filters: Optional[dict] = None) -> dict:
    ds = get_dataset()
    d = parse_date(date_str)
    f = filters or {}
    out = []
    for sid in ds.by_date.get(d, []):
        s = ds.sessions[sid]
        if f.get("lecturer_id") and s.lecturer_id != f["lecturer_id"].upper():
            continue
        if f.get("room") and s.room != f["room"]:
            continue
        if f.get("school") and s.school != f["school"].upper():
            continue
        if f.get("intake") and not any(g[0] == f["intake"].upper() for g in s.groups):
            continue
        if f.get("room_type") and ds.rooms[s.room].type != f["room_type"]:
            continue
        if f.get("after"):
            h, m = map(int, f["after"].split(":"))
            if s.start_min < h * 60 + m:
                continue
        out.append(s)
    out.sort(key=lambda s: (s.start_min, s.room))
    rows = [sdict(ds, s) for s in out]
    limit = int(f.get("limit", 2000))
    return {
        "date": d.isoformat(),
        "count": len(rows),
        "intake_rows": sum(len(s.groups) for s in out),
        "students": sum(r["students"] for r in rows),
        "sessions": rows[:limit],
        "truncated": len(rows) > limit,
    }


def _lect_suggest(ds: Dataset, q: str) -> list[str]:
    return difflib.get_close_matches(q, list(ds.by_lecturer), n=5, cutoff=0.4)


def _intake_suggest(ds: Dataset, q: str) -> list[str]:
    return difflib.get_close_matches(q, list(ds.by_intake), n=5, cutoff=0.5)


def search_lecturers(query: str, limit: int = 10) -> dict:
    ds = get_dataset()
    q = (query or "").strip().upper()
    require(len(q) >= 1, "EMPTY_QUERY", "query required")
    scored = []
    for lid, name in ds.lecturer_names.items():
        mods = {ds.sessions[i].module_name for i in ds.by_lecturer[lid]}
        hay = f"{lid} {name} {' '.join(mods)}".upper()
        if lid == q:
            score = 1.0
        elif q in hay:
            score = 0.9 if lid.startswith(q) else 0.7
        else:
            score = difflib.SequenceMatcher(None, q, lid).ratio() * 0.6
        if score > 0.35:
            scored.append((score, lid, name, sorted(mods)[:5]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return {
        "query": query,
        "results": [
            {"lecturer_id": l, "lecturer_name": n, "modules": m, "sessions_in_window": len(ds.by_lecturer[l]), "score": round(s, 2)}
            for s, l, n, m in scored[:limit]
        ],
    }


def search_intakes(query: str, limit: int = 10) -> dict:
    ds = get_dataset()
    q = (query or "").strip().upper()
    require(len(q) >= 2, "EMPTY_QUERY", "query must be >= 2 chars")
    res = []
    for intake, groups in ds.by_intake.items():
        if q in intake:
            score = 1.0 if intake == q else (0.9 if intake.startswith(q) else 0.7)
        else:
            score = difflib.SequenceMatcher(None, q, intake).ratio() * 0.8
        if score > 0.5:
            res.append((score, intake, sorted(groups)))
    res.sort(key=lambda x: (-x[0], x[1]))
    return {
        "query": query,
        "results": [
            {
                "intake": i,
                "groupings": g,
                "students": sum(ds.group_sizes.get((i, x), 0) for x in g),
                "score": round(s, 2),
            }
            for s, i, g in res[:limit]
        ],
    }


def timetable_health(start_date: str, end_date: str, max_items: int = 50) -> dict:
    """Long gaps (> 3h idle between classes), > 3 back-to-back sessions, days > 6h, lecturer load."""
    ds = get_dataset()
    a, b = date_range(start_date, end_date)
    long_gaps, b2b, long_days = [], [], []
    for g, ids in ds.by_group.items():
        per_day: dict[date, list[Session]] = defaultdict(list)
        for i in ids:
            s = ds.sessions[i]
            if a <= s.date <= b:
                per_day[s.date].append(s)
        for d, ss in per_day.items():
            ss.sort(key=lambda s: s.start_min)
            total = sum(s.duration for s in ss)
            if total > 360:
                long_days.append({"intake": g[0], "grouping": g[1], "date": d.isoformat(), "hours": round(total / 60, 2)})
            run = 1
            for x, y in zip(ss, ss[1:]):
                gap = y.start_min - x.end_min
                if gap > 180:
                    long_gaps.append(
                        {"intake": g[0], "grouping": g[1], "date": d.isoformat(), "gap_hours": round(gap / 60, 2),
                         "between": f"{x.end_iso()[11:16]}-{y.start_iso()[11:16]}"}
                    )
                run = run + 1 if gap <= 30 else 1
                if run == 4:
                    b2b.append({"intake": g[0], "grouping": g[1], "date": d.isoformat(), "consecutive": run})
    lect_load = []
    for lid, ids in ds.by_lecturer.items():
        mins = sum(ds.sessions[i].duration for i in ids if a <= ds.sessions[i].date <= b)
        if mins:
            days = len({ds.sessions[i].date for i in ids if a <= ds.sessions[i].date <= b})
            lect_load.append({"lecturer_id": lid, "lecturer_name": ds.lecturer_names[lid], "hours": round(mins / 60, 1), "teaching_days": days})
    lect_load.sort(key=lambda x: -x["hours"])
    weeks = max(1, ((b - a).days + 1) / 7)
    hist = Counter(int(x["hours"] / weeks // 2 * 2) for x in lect_load)
    long_days.sort(key=lambda x: -x["hours"])
    long_gaps.sort(key=lambda x: -x["gap_hours"])
    by_dow = Counter()
    for x in long_days:
        by_dow[date.fromisoformat(x["date"]).strftime("%a")] += 1
    return {
        "range": {"start": a.isoformat(), "end": b.isoformat()},
        "summary": {
            "groups_analysed": len(ds.by_group),
            "long_gaps": len(long_gaps),
            "back_to_back_4plus": len(b2b),
            "days_over_6h": len(long_days),
            "lecturers": len(lect_load),
        },
        "long_days_by_weekday": dict(by_dow),
        "lecturer_load_histogram_hours_per_week": [{"bucket": f"{k}-{k + 2}h", "lecturers": v} for k, v in sorted(hist.items())],
        "long_gaps": long_gaps[:max_items],
        "back_to_back": b2b[:max_items],
        "long_days": long_days[:max_items],
        "lecturer_load": lect_load[:max_items],
    }


def overview_stats() -> dict:
    from ..config import settings

    ds = get_dataset()
    today = settings.now().date()
    tids = ds.by_date.get(today, [])
    week = [today + timedelta(days=i) for i in range(7)]
    return {
        "snapshot": {k: v for k, v in ds.meta.items() if k != "stats"} | {"stats": {k: v for k, v in ds.meta.get("stats", {}).items() if k != "rows_per_day"}},
        "now": settings.now().isoformat(),
        "today": today.isoformat(),
        "rows": len(ds.rows),
        "physical_sessions": len(ds.sessions),
        "intakes": len(ds.by_intake),
        "lecturers": len(ds.by_lecturer),
        "rooms": len([r for r in ds.rooms.values() if r.name != "ONLINE"]),
        "today_sessions": len(tids),
        "today_students": sum(ds.session_students(ds.sessions[i]) for i in tids),
        "week_sessions_per_day": [{"date": d.isoformat(), "day": d.strftime("%a"), "sessions": len(ds.by_date.get(d, []))} for d in week],
        "date_coverage": {"from": ds.dates[0].isoformat(), "to": ds.dates[-1].isoformat()},
    }
