"""Substitute lecturer finder (Replan, first resort for LECTURER_UNAVAILABLE).

A substitute must (R-SUB-MODULE) genuinely teach the same module somewhere in the timetable, (R-SUB-FREE) be free for
the whole session, and (R-SUB-LOAD) stay within a daily load cap (default 3 sessions/day including this one).
Ranking: teaches the exact module section (same MODID) > same module (MODID without section suffix, or same module
name); then same school (CLASS_CODE prefix); then the lowest load that day.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Optional

from ..data.indexes import BusyIndex
from ..data.loader import Dataset, get_dataset
from ..domain import hhmm
from .errors import NotFound

MAX_DAILY_SESSIONS = int(os.environ.get("SUB_MAX_DAILY_SESSIONS", "3"))
_SECTION = re.compile(r"-[A-Z]+-\d+$")


def module_base(modid: str) -> str:
    """'CT044-3-1-IOOP-LAB-28' -> 'CT044-3-1-IOOP'; 'MPU1132-BMK1(FS)-L-6 (Online)' -> 'MPU1132-BMK1(FS)'."""
    m = re.sub(r"\s*\((?i:online)\)\s*$", "", modid.strip())
    return _SECTION.sub("", m)


def _index(ds: Dataset) -> dict:
    idx = ds.__dict__.get("_sub_index")
    if idx is None:
        sec, base, name = defaultdict(set), defaultdict(set), defaultdict(set)
        school = defaultdict(set)
        for s in ds.sessions.values():
            for mid in s.module_ids:
                sec[mid].add(s.lecturer_id)
                base[module_base(mid)].add(s.lecturer_id)
            name[s.module_name.strip().lower()].add(s.lecturer_id)
            school[s.lecturer_id].add(s.school)
        idx = {"section": sec, "base": base, "name": name, "school": school}
        ds.__dict__["_sub_index"] = idx
    return idx


def teaches(ds: Dataset, lecturer_id: str, session) -> Optional[str]:
    """'section' | 'module' | None - does this lecturer genuinely teach the session's module?"""
    idx = _index(ds)
    if any(lecturer_id in idx["section"].get(m, ()) for m in session.module_ids):
        return "section"
    if any(lecturer_id in idx["base"].get(module_base(m), ()) for m in session.module_ids) or \
            lecturer_id in idx["name"].get(session.module_name.strip().lower(), ()):
        return "module"
    return None


def sessions_that_day(ds: Dataset, lecturer_id: str, d, overlay: Optional[BusyIndex] = None) -> int:
    n = len(ds.lect_busy.intervals(lecturer_id, d))
    if overlay is not None:
        n += len(overlay.intervals(lecturer_id, d))
    return n


def find_substitutes(session_id: str, exclude: Optional[list[str]] = None, max_daily_sessions: Optional[int] = None,
                     overlay: Optional[BusyIndex] = None, limit: int = 5) -> dict:
    ds = get_dataset()
    s = ds.sessions.get(session_id)
    if not s:
        raise NotFound("UNKNOWN_SESSION", f"No session {session_id}")
    cap = max_daily_sessions or MAX_DAILY_SESSIONS
    idx = _index(ds)
    pool: set[str] = set()
    for m in s.module_ids:
        pool |= idx["section"].get(m, set()) | idx["base"].get(module_base(m), set())
    pool |= idx["name"].get(s.module_name.strip().lower(), set())
    skip = {s.lecturer_id, *(x.upper() for x in (exclude or []))}
    ranked, rejected = [], defaultdict(int)
    for lid in sorted(pool - skip):
        tier = teaches(ds, lid, s)
        if not tier:
            continue
        if not ds.lect_busy.is_free(lid, s.date, s.start_min, s.end_min) or (overlay and not overlay.is_free(lid, s.date, s.start_min, s.end_min)):
            rejected["busy at that time"] += 1
            continue
        load = sessions_that_day(ds, lid, s.date, overlay)
        if load + 1 > cap:
            rejected[f"would exceed {cap} sessions that day"] += 1
            continue
        same_school = s.school in idx["school"].get(lid, set())
        score = (200 if tier == "section" else 100) + (10 if same_school else 0) - load
        ranked.append({
            "lecturer_id": lid, "lecturer_name": ds.lecturer_names.get(lid, lid), "match": tier, "same_school": same_school,
            "sessions_that_day": load, "score": score,
            "reason": (f"teaches the {'same module section' if tier == 'section' else 'same module'}"
                       f"{' in the same school' if same_school else ''}; free {hhmm(s.start_min)}-{hhmm(s.end_min)}; "
                       f"{load} other session(s) that day (cap {cap})"),
        })
    ranked.sort(key=lambda r: (-r["score"], r["lecturer_id"]))
    return {"session_id": session_id, "module_name": s.module_name, "module_ids": s.module_ids, "lecturer_id": s.lecturer_id,
            "slot": f"{s.date.isoformat()} {hhmm(s.start_min)}-{hhmm(s.end_min)}", "room": s.room,
            "candidates": ranked[:limit], "considered": len(pool - skip), "rejected": dict(rejected), "daily_cap": cap}
