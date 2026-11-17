"""Gemini fallback for the in-app assistant.

The rule-based assistant handles the core operations instantly and offline (disruptions, approvals, slots, attendance).
Anything it does not recognise is answered here by Gemini (Gemini API, function calling) using READ-ONLY tools over the
same services the MCP server exposes. Gemini can look things up and explain; it cannot create disruptions, draft,
approve or execute anything - those stay on the explicit, human-approved path (R-HITL).

Tools are scoped to the signed-in role: a student only gets their own timetable and attendance.
Enabled when GEMINI_API_KEY (or GOOGLE_API_KEY) is set. Any failure returns None so the caller falls back to help text.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import timedelta
from typing import Any, Callable, Optional

import requests

from ..config import settings
from . import attendance, holidays, proposals, replan, rooms, shuttle, slots, substitutes, timetable
from .errors import ToolError
from .identity import Identity
from .policy import get_policy as _get_policy

log = logging.getLogger("campus.gemini")
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_ROUNDS = 5
BUDGET_S = 25.0
RESULT_CHARS = 14000


def _key() -> str:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


def model() -> str:
    return os.environ.get("CHAT_GEMINI_MODEL", "gemini-3.5-flash-lite")


def enabled() -> bool:
    return bool(_key()) and os.environ.get("CHAT_GEMINI", "on").lower() not in ("0", "off", "false")


# ------------------------------------------------------------------ tool registry
S, I, B = "STRING", "INTEGER", "BOOLEAN"


def _decl(name: str, desc: str, props: dict[str, tuple[str, str]], required: tuple[str, ...] = ()) -> dict:
    d: dict[str, Any] = {"name": name, "description": desc}
    if props:
        d["parameters"] = {"type": "OBJECT", "properties": {k: {"type": t, "description": ds} for k, (t, ds) in props.items()},
                           "required": list(required)}
    return d


def _tools(who: Identity, planning: bool = False) -> dict[str, tuple[dict, Callable[..., Any]]]:
    t: dict[str, tuple[dict, Callable[..., Any]]] = {}

    def add(name, desc, props, required, fn):
        t[name] = (_decl(name, desc, props, required), fn)

    DATE = (S, "YYYY-MM-DD")
    add("search_lecturers", "Search lecturers by id (e.g. 'MZD'), pseudonymised name or module name.", {"query": (S, "text")}, ("query",),
        lambda query: timetable.search_lecturers(query))
    add("get_holidays", "APU public and university holidays for a year, plus holidays declared in the system.", {"year": (I, "e.g. 2026")}, (),
        lambda year=2026: holidays.get_holidays(int(year)))
    add("get_last_shuttle", "Last campus shuttle departure on a date and the latest end time for physical make-up classes.", {"date": DATE}, ("date",),
        lambda date: shuttle.get_last_shuttle(date))
    add("get_policy", "All operational rules (R-* ids) with their source and label (QUOTED / ASSUMPTION / VERIFY).", {}, (),
        lambda: _get_policy())
    add("find_free_rooms", "Rooms free for a whole window on one day.",
        {"start": (S, "ISO datetime, MYT, e.g. 2026-11-13T14:00:00+08:00"), "end": (S, "ISO datetime, same day"),
         "min_capacity": (I, "minimum seats"), "room_type": (S, "classroom|lab|auditorium|specialist_lab|discussion|presentation")},
        ("start", "end"), lambda start, end, min_capacity=0, room_type=None: rooms.find_free_rooms(start, end, int(min_capacity or 0), room_type, 30))
    add("get_room_schedule", "All classes in one room on a date, plus the room's type and capacity.", {"room": (S, "e.g. B-04-03"), "date": DATE},
        ("room", "date"), lambda room, date: rooms.get_room_schedule(room, date))
    add("empty_rooms_now", "Physical rooms with no class right now and how long each stays free.", {}, (), lambda: rooms.empty_rooms_now(None))

    if who.role == "student":
        rec = attendance.get_student_record(who.user)
        add("my_timetable", f"The signed-in student's own classes ({rec['intake']} / {rec['grouping']}) between two dates, inclusive.",
            {"start_date": DATE, "end_date": DATE}, ("start_date", "end_date"),
            lambda start_date, end_date: timetable.get_group_schedule(rec["intake"], rec["grouping"], start_date, end_date))
        add("my_attendance", "The signed-in student's attendance: current %, per-module %, remaining classes and how many more "
            "they can miss per module before dropping below the threshold.", {}, (), lambda: _forecast(who.user))
        add("my_absences", "The signed-in student's attendance history so far: classes held, attended and missed (overall and per "
            "module), and the list of every missed class with module, date and time.", {}, (), lambda: _absences(who.user))
        return t

    add("get_lecturer_schedule", "Classes taught by a lecturer between two dates, inclusive.", {"lecturer_id": (S, "e.g. MZD"), "start_date": DATE, "end_date": DATE},
        ("lecturer_id", "start_date", "end_date"), lambda lecturer_id, start_date, end_date: timetable.get_lecturer_schedule(lecturer_id.upper(), start_date, end_date))
    add("get_group_schedule", "Classes for an intake (optionally one grouping G1..G6) between two dates.",
        {"intake": (S, "e.g. APD2F2609DA"), "start_date": DATE, "end_date": DATE, "grouping": (S, "G1..G6, optional")}, ("intake", "start_date", "end_date"),
        lambda intake, start_date, end_date, grouping=None: timetable.get_group_schedule(intake.upper(), grouping, start_date, end_date))
    add("get_sessions_on", "Classes on one date with optional filters.",
        {"date": DATE, "lecturer_id": (S, "optional"), "room": (S, "optional"), "school": (S, "optional"), "intake": (S, "optional"),
         "after": (S, "HH:MM, optional: only classes starting at/after this time")}, ("date",),
        lambda date, **f: timetable.get_sessions_on(date, {k: v for k, v in f.items() if v} | {"limit": 80}))
    add("search_intakes", "Search intake codes.", {"query": (S, "e.g. APD3F2505")}, ("query",), lambda query: timetable.search_intakes(query))
    add("get_room_utilisation", "Average utilisation per room per hour over working days in a date range.",
        {"start_date": DATE, "end_date": DATE, "room_type": (S, "optional")}, ("start_date", "end_date"),
        lambda start_date, end_date, room_type=None: rooms.get_room_utilisation(start_date, end_date, room_type))
    add("timetable_health", "Long gaps, back-to-back blocks, long days per intake group and lecturer load in a date range.",
        {"start_date": DATE, "end_date": DATE}, ("start_date", "end_date"), lambda start_date, end_date: timetable.timetable_health(start_date, end_date, 25))
    add("list_proposals", "List re-planning and booking proposals. status: DRAFT|APPROVED|EXECUTED|REJECTED|SUPERSEDED.", {"status": (S, "optional")}, (),
        lambda status=None: proposals.list_proposals(status, None))
    add("explain_proposal", "Plain-language summary of one proposal (e.g. PRO-0001).", {"proposal_id": (S, "e.g. PRO-0001")}, ("proposal_id",),
        lambda proposal_id: replan.explain_proposal(proposal_id))
    add("find_substitutes", "Lecturers who teach the same module, are free for the whole class and within their daily load.",
        {"session_id": (S, "a session id from a schedule result")}, ("session_id",), lambda session_id: substitutes.find_substitutes(session_id, None))
    add("find_common_slots", "Times when all the given intakes and lecturers are free, with a suitable room. Read-only search: it books nothing.",
        {"groups": (S, "comma-separated intakes, e.g. 'AFCF2509BA,AFCF2609BA' (may be empty)"),
         "lecturer_ids": (S, "comma-separated lecturer ids, e.g. 'CMM,MSB' (may be empty)"),
         "duration_min": (I, "minutes"), "window_start": DATE, "window_end": DATE, "room_type": (S, "optional")},
        ("duration_min", "window_start", "window_end"),
        lambda duration_min, window_start, window_end, groups="", lecturer_ids="", room_type=None: slots.find_common_slots(
            _csv(groups), [x.upper() for x in _csv(lecturer_ids)], int(duration_min), {"start": window_start, "end": window_end},
            {"type": room_type} if room_type else None, 1))
    if planning:
        add("draft_replan", "Re-plan after a disruption and return a DRAFT plan (substitute lecturers first, then a clash-free reschedule "
            "by the OR-Tools CP-SAT solver). It never approves or applies anything. kind: LECTURER_UNAVAILABLE (needs lecturer_id, "
            "start_date, end_date), ROOM_UNAVAILABLE (needs rooms, end_date) or HOLIDAY (needs start_date = the holiday).",
            {"kind": (S, "LECTURER_UNAVAILABLE | ROOM_UNAVAILABLE | HOLIDAY"), "lecturer_id": (S, "e.g. MZD"),
             "rooms": (S, "comma-separated, e.g. B-04-03"), "start_date": DATE, "end_date": DATE, "reason": (S, "short reason")},
            ("kind",), _draft_replan)
    if who.role == "admin":
        add("attendance_forecast", "One (synthetic) student's attendance forecast and how many more classes they can miss.",
            {"student_id": (S, "e.g. STU-DEMO-01")}, ("student_id",), lambda student_id: _forecast(student_id.upper()))
        add("attendance_risk_list", "Students below or heading towards the attendance threshold (read-only).", {"limit": (I, "max rows")}, (),
            lambda limit=20: attendance.attendance_risk_list(None, int(limit)))
    return t


def _draft_replan(kind: str, lecturer_id: str = "", rooms: str = "", start_date: str = "", end_date: str = "", reason: str = "") -> dict:
    """Create the disruption and a DRAFT plan (substitutes first, then CP-SAT). Never approves or executes."""
    k = (kind or "").strip().upper()
    if k in ("LECTURER", "LECTURER_UNAVAILABLE", "SICK"):
        if not lecturer_id:
            return {"error": "lecturer_id is required"}
        b = end_date or start_date
        d = replan.create_disruption("LECTURER_UNAVAILABLE", {"lecturer_id": lecturer_id.upper()}, {"start": start_date, "end": b}, reason, "Gemini Enterprise agent")
    elif k in ("ROOM", "ROOM_UNAVAILABLE"):
        rms = [r.upper() for r in _csv(rooms)]
        if not rms:
            return {"error": "rooms is required"}
        d = replan.create_disruption("ROOM_UNAVAILABLE", {"rooms": rms}, {"start": settings.now().isoformat(), "end": end_date or start_date},
                                     reason, "Gemini Enterprise agent")
    elif k in ("HOLIDAY", "CAMPUS_HOLIDAY"):
        d = replan.create_disruption("HOLIDAY", {"date": start_date, "name": reason or "Declared public holiday"}, None, reason, "Gemini Enterprise agent")
    else:
        return {"error": "kind must be LECTURER_UNAVAILABLE, ROOM_UNAVAILABLE or HOLIDAY"}
    if not d["impact"]["sessions"]:
        return {"headline": d["headline"], "note": "No upcoming classes in that window: nothing to re-plan."}
    pr = replan.plan_replan(d["id"], {}, created_by="Gemini Enterprise agent")
    ex = replan.explain_proposal(pr["id"])
    return {"headline": d["headline"], "proposal_id": pr["id"], "status": pr["status"], "summary": ex["text"],
            "moves": ex.get("table", [])[:8], "note": "DRAFT only. A person must approve it in the Campus Time Ops app."}


def _csv(s: Any) -> list[str]:
    if isinstance(s, list):
        return [str(x).strip() for x in s if str(x).strip()]
    return [x.strip() for x in str(s or "").split(",") if x.strip()]


def _absences(sid: str) -> dict:
    g = attendance.get_attendance(sid)
    missed = [{k: r[k] for k in ("module", "date", "time")} for r in g["records"] if r["status"] == "ABSENT"]
    return {"held_so_far": g["sessions_so_far"], "attended": g["attended"], "missed": len(missed), "percent": g["percent"],
            "by_module": [{**m, "missed": m["held"] - m["attended"]} for m in g["by_module"]], "missed_classes": missed}


def _forecast(sid: str) -> dict:
    f = attendance.attendance_forecast(sid)
    f.pop("weekly", None)
    return f


def _slim(x: Any, depth: int = 0) -> Any:
    if isinstance(x, list):
        out = [_slim(v, depth + 1) for v in x[:40]]
        if len(x) > 40:
            out.append(f"... {len(x) - 40} more")
        return out
    if isinstance(x, dict):
        return {k: _slim(v, depth + 1) for k, v in x.items() if k not in ("color", "COLOR", "raw", "weekly")}
    return x


# ------------------------------------------------------------------ prompt
def _system(who: Identity, planning: bool = False) -> str:
    now = settings.now()
    tomorrow = now + timedelta(days=1)
    role = {"student": f"a student ({who.user})", "lecturer": f"lecturer {who.user}", "admin": "the APU timetabling office"}.get(who.role, "staff")
    student_rule = ("This user is a STUDENT: students cannot change the timetable or report anything. If they want a change, tell them to "
                    "contact their lecturer or the timetabling office. Never suggest the sentences above to a student."
                    if who.role == "student" else "Staff may type the sentences above to start a change.")
    return f"""You are {"the Campus Time Ops agent inside Gemini Enterprise" if planning else "the Campus Time Ops assistant"} for Asia Pacific University (APU), Kuala Lumpur.
You are talking to {role}. Now is {now:%A %d %B %Y, %H:%M} (Malaysia time, MYT, UTC+8). Tomorrow is {tomorrow:%A %d %B %Y}.
Weeks run Monday to Friday. The timetable data covers about 10-28 November 2026.

Rules:
- Use the tools for every fact about classes, rooms, lecturers, holidays, shuttles and attendance. Never invent data. If a tool returns an error or nothing, say so plainly.
{ "- You can LOOK THINGS UP and DRAFT re-plans with draft_replan (when the user reports a sick/unavailable lecturer, a closed room or a holiday). "
   "Report the draft clearly: classes affected, students, how many covered by a substitute, how many moved and where, and the proposal id. "
   "You can NEVER approve, apply or send anything: say a person reviews and approves the draft in the Campus Time Ops app."
   if planning else "- You can only LOOK THINGS UP and explain. You cannot change the timetable, create plans, approve or send anything." }
  If the user wants a change, tell them the exact sentence to type, e.g. "I'm sick tomorrow, sort out my classes", "Room B-04-03 is flooded until Friday",
  "Monday 16 Nov is now a public holiday" or "find a 45 minute slot next week for 6 vivas with CMM, MSB and RJR". Those go through a plan a person must approve.
- {student_rule}
- Lecturers are identified by short pseudonymised ids (e.g. MZD); student data is synthetic. Attendance threshold is 80% per module (APU Student Handbook).
- {"Answer in plain English, short. After a draft, use up to 6 short lines." if planning else "Answer in 1-4 short sentences of plain English."} Lead with the answer. Use **bold** for the key number or name. No tables, no headings, no lists longer than 4 items.
- Times as 24h HH:MM, dates like "Fri 13 Nov"."""


# ------------------------------------------------------------------ call loop
def _post(body: dict, timeout: float) -> dict:
    r = requests.post(API.format(model=model()), headers={"x-goog-api-key": _key(), "content-type": "application/json"},
                      data=json.dumps(body, default=str), timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def answer(message: str, who: Identity, planning: bool = False, history: Optional[list[dict]] = None,
           budget_s: float = BUDGET_S) -> Optional[dict]:
    """-> {"reply", "cards", "engine": "gemini", "tools_used"} or None if Gemini is off or failed.
    planning=True (Gemini Enterprise agent) adds draft_replan; history = earlier [{"role": "user"|"model", "text": ...}]."""
    if not _key():
        return None
    if not planning and not enabled():
        return None
    t0 = time.monotonic()
    try:
        tools = _tools(who, planning)
    except ToolError:
        return None
    past = [{"role": h["role"], "parts": [{"text": h["text"][:3000]}]} for h in (history or [])[-10:]]
    body: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": _system(who, planning)}]},
        "contents": past + [{"role": "user", "parts": [{"text": message[:2000]}]}],
        "tools": [{"functionDeclarations": [d for d, _ in tools.values()]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 900 if planning else 600},
    }
    m = model()
    if m.startswith("gemini-2.5-flash"):
        body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
    elif m.startswith("gemini-3"):
        body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": os.environ.get("CHAT_GEMINI_THINKING", "low")}
    used: list[str] = []
    sched: Optional[tuple[str, list]] = None
    try:
        for _ in range(MAX_ROUNDS):
            left = budget_s - (time.monotonic() - t0)
            if left < 2:
                log.warning("Gemini fallback: time budget used up after %s", used)
                return None
            data = _post(body, timeout=min(25.0, left))
            cand = (data.get("candidates") or [{}])[0]
            parts = (cand.get("content") or {}).get("parts") or []
            calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if not calls:
                text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
                if not text:
                    return None
                cards = []
                if sched:
                    from .assistant import _sched_card
                    cards.append(_sched_card(sched[0], sched[1]))
                return {"reply": text, "cards": cards, "engine": "gemini", "tools_used": used}
            body["contents"].append({"role": "model", "parts": parts})
            responses = []
            for c in calls:
                name, args = c.get("name", ""), c.get("args") or {}
                used.append(name)
                if name not in tools:
                    result: Any = {"error": f"unknown tool {name}"}
                else:
                    try:
                        result = tools[name][1](**args)
                    except ToolError as e:
                        result = e.to_dict()
                    except TypeError as e:
                        result = {"error": f"bad arguments: {e}"}
                if name in ("my_timetable", "get_lecturer_schedule", "get_group_schedule") and isinstance(result, dict) and result.get("sessions"):
                    sched = (f"{args.get('lecturer_id') or args.get('intake') or 'My timetable'} · {args.get('start_date')} – {args.get('end_date')}",
                             result["sessions"])
                payload = json.dumps(_slim(result), default=str)
                if len(payload) > RESULT_CHARS:
                    payload = payload[:RESULT_CHARS] + '..." (truncated)'
                responses.append({"functionResponse": {"name": name, "response": {"result": payload}}})
            body["contents"].append({"role": "user", "parts": responses})
        return None
    except Exception as e:  # network, quota, bad response: the caller falls back to the help text
        log.warning("Gemini fallback failed: %s", str(e).replace(_key(), "<key>")[:400])
        return None
