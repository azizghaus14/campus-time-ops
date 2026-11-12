"""Campus MCP Server: the same service functions as the REST API, exposed as MCP tools over streamable HTTP.

Run standalone:  python -m app.mcp_server            (streamable HTTP on :8001/mcp)
                 python -m app.mcp_server --stdio    (for MCP Inspector / local clients)
Inside the main app it is mounted at /mcp (see main.py), protected by a bearer token (MCP_AUTH_TOKEN).
"""
from __future__ import annotations

import functools
import sys
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .services import attendance, holidays, proposals, replan, rooms, shuttle, slots, substitutes, timetable
from .services.errors import ToolError
from .services.policy import get_policy as _get_policy

INSTRUCTIONS = """Campus Time Ops - AI operations layer on APU's live timetable (pseudonymised public feed).
Read tools are free to call. Planning tools create DRAFT proposals only. The action tool (execute_proposal) refuses
anything that is not APPROVED: only call approve_proposal after the human user has explicitly said yes in chat (R-HITL).
The system only creates Gmail DRAFTS; humans send them. Always state counts (sessions, groups, students) and cite rule ids (R-*) from the proposal citations.
Times are MYT (UTC+8). Lecturers are identified by short ids like 'MDD'; groups by (intake, grouping) e.g. AFCF2509BA/G1."""

mcp = FastMCP(
    "campus-time-ops",
    instructions=INSTRUCTIONS,
    stateless_http=True,
    json_response=True,
    streamable_http_path="/mcp",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _safe(fn):
    @functools.wraps(fn)
    def w(*a, **k):
        try:
            return fn(*a, **k)
        except ToolError as e:
            return e.to_dict()

    return w


def tool(fn):
    mcp.add_tool(_safe(fn), name=fn.__name__, description=(fn.__doc__ or "").strip())
    return fn


# ------------------------------------------------------------- read tools
@tool
def get_lecturer_schedule(lecturer_id: str, start_date: str, end_date: str) -> dict:
    """Physical sessions taught by a lecturer between two dates (YYYY-MM-DD, inclusive). lecturer_id e.g. 'MDD'."""
    return timetable.get_lecturer_schedule(lecturer_id, start_date, end_date)


@tool
def get_group_schedule(intake: str, start_date: str, end_date: str, grouping: Optional[str] = None) -> dict:
    """Sessions for an intake (optionally one grouping G1..G6) between two dates."""
    return timetable.get_group_schedule(intake, grouping, start_date, end_date)


@tool
def get_room_schedule(room: str, date: str) -> dict:
    """All sessions in a room on a date, plus the room's type and (mock) capacity."""
    return rooms.get_room_schedule(room, date)


@tool
def find_free_rooms(start: str, end: str, min_capacity: int = 0, room_type: Optional[str] = None) -> dict:
    """Rooms free for the whole window (ISO datetimes, same day). room_type: classroom|lab|auditorium|specialist_lab|discussion|presentation."""
    return rooms.find_free_rooms(start, end, min_capacity, room_type)


@tool
def get_sessions_on(date: str, lecturer_id: Optional[str] = None, room: Optional[str] = None, school: Optional[str] = None,
                    intake: Optional[str] = None, room_type: Optional[str] = None, after: Optional[str] = None, limit: int = 200) -> dict:
    """Sessions on a date with optional filters (after='15:00' keeps sessions starting at/after 15:00)."""
    f = {k: v for k, v in dict(lecturer_id=lecturer_id, room=room, school=school, intake=intake, room_type=room_type, after=after, limit=limit).items() if v}
    return timetable.get_sessions_on(date, f)


@tool
def search_lecturers(query: str) -> dict:
    """Fuzzy search lecturers by id, pseudonymised name or module name."""
    return timetable.search_lecturers(query)


@tool
def search_intakes(query: str) -> dict:
    """Fuzzy search intake codes (e.g. 'APD3F2505')."""
    return timetable.search_intakes(query)


@tool
def get_holidays(year: int = 2026) -> dict:
    """APU public + university holidays for a year (source: apu.edu.my holiday schedule) plus holidays declared via disruptions."""
    return holidays.get_holidays(year)


@tool
def get_last_shuttle(date: str) -> dict:
    """Last campus shuttle departure on a date and the latest allowed end time for physical make-up classes (R-SHUTTLE)."""
    return shuttle.get_last_shuttle(date)


@tool
def get_room_utilisation(start_date: str, end_date: str, room_type: Optional[str] = None) -> dict:
    """Average utilisation per room per hour (08:00-21:00) over working days in range."""
    return rooms.get_room_utilisation(start_date, end_date, room_type)


@tool
def empty_rooms_now(at: Optional[str] = None) -> dict:
    """Physical rooms with no class at a moment (default: now) and how long each stays free."""
    return rooms.empty_rooms_now(at)


@tool
def timetable_health(start_date: str, end_date: str) -> dict:
    """Long gaps, 4+ back-to-back sessions, days over 6 hours per intake group, lecturer load, online vs physical mix by hour."""
    return timetable.timetable_health(start_date, end_date, 25)


@tool
def get_policy() -> dict:
    """All operational rules (R-* ids) with labels QUOTED/ASSUMPTION/VERIFY and current thresholds."""
    return _get_policy()


# ------------------------------------------------------------- planning tools
@tool
def create_disruption(type: str, scope: dict[str, Any], window: Optional[dict[str, str]] = None, reason: str = "", created_by: str = "agent") -> dict:
    """Register a disruption and compute its impact. type: LECTURER_UNAVAILABLE (scope {lecturer_id}) | ROOM_UNAVAILABLE
    (scope {rooms:[...]}) | HOLIDAY (scope {date}). window {start,end} as ISO dates/datetimes (MYT). Returns affected
    sessions and a headline like 'This affects 4 sessions, 9 intake groups and ~310 students.' No side effects."""
    d = replan.create_disruption(type, scope, window, reason, created_by)
    d["affected_sessions"] = d.get("affected_sessions", [])[:25]
    d.pop("affected_session_ids", None)
    return d


@tool
def find_substitutes(session_id: str, exclude: Optional[list[str]] = None) -> dict:
    """Lecturers who genuinely teach the same module (same MODID section, or same module), are free for the whole session
    and stay within the daily load cap (default 3 sessions/day). Ranked: same section > same module; same school; lowest load."""
    return substitutes.find_substitutes(session_id, exclude)


@tool
def plan_replan(disruption_id: str, horizon_days: int = 10, allow_online: bool = True, preferred_slots: Optional[list[str]] = None,
                max_moves_per_group_per_week: Optional[int] = None, allow_saturday: bool = False,
                pins: Optional[dict[str, dict[str, Any]]] = None, use_substitutes: bool = True,
                decline_substitutes: Optional[list[str]] = None) -> dict:
    """Return a DRAFT proposal. For LECTURER_UNAVAILABLE each session first gets a substitute lecturer (same time + room, no
    student affected); the rest are rescheduled by the CP-SAT solver. Every move has type SUBSTITUTE | RESCHEDULE | ONLINE;
    unresolved sessions are listed with reasons. Edits: pins = {session_id: {"date": "YYYY-MM-DD", "period":
    "morning|afternoon|evening", "start": "HH:MM", "room": "...", "online": true}} (a pinned session is rescheduled, not
    substituted); decline_substitutes = [session_id] to reschedule instead. Re-planning supersedes the previous draft."""
    o = {k: v for k, v in dict(horizon_days=horizon_days, allow_online=allow_online, preferred_slots=preferred_slots,
                               max_moves_per_group_per_week=max_moves_per_group_per_week, allow_saturday=allow_saturday,
                               pins=pins, use_substitutes=use_substitutes, decline_substitutes=decline_substitutes).items() if v is not None}
    p = replan.plan_replan(disruption_id, o)
    return replan.proposal_view(p, move_limit=25)


@tool
def explain_proposal(proposal_id: str) -> dict:
    """Plain-language summary + compact table of a proposal, ready to show the user."""
    return replan.explain_proposal(proposal_id)


@tool
def get_proposal(proposal_id: str) -> dict:
    """Full proposal (moves truncated to 50 for large proposals)."""
    return replan.proposal_view(proposals.get_proposal(proposal_id), move_limit=50)


@tool
def list_proposals(status: Optional[str] = None, kind: Optional[str] = None) -> list[dict]:
    """List proposals (compact). status: DRAFT|APPROVED|EXECUTED|REJECTED|SUPERSEDED; kind: REPLAN|SLOT_BOOKING."""
    return proposals.list_proposals(status, kind)


@tool
def find_common_slots(groups: list[str], lecturer_ids: list[str], duration_min: int, window_start: str, window_end: str,
                      room_type: Optional[str] = None, min_capacity: Optional[int] = None, count: int = 1, online: bool = False) -> dict:
    """Slot Finder: ranked top-3 slots where all groups ('INTAKE' or 'INTAKE/G1') and lecturers/examiners are free plus a suitable
    room. count>1 finds a contiguous block (e.g. 6 back-to-back 45-min vivas, same panel + room)."""
    rr = {"type": "online" if online else room_type, "min_capacity": min_capacity}
    return slots.find_common_slots(groups, lecturer_ids, duration_min, {"start": window_start, "end": window_end}, rr, count)


@tool
def create_slot_proposal(title: str, start: str, end: str, groups: list[str], lecturer_ids: list[str], room: str,
                         description: str = "", sub_slots: Optional[list[dict[str, str]]] = None) -> dict:
    """Turn a chosen slot into a DRAFT booking proposal (calendar invites + email drafts are created only after approval)."""
    return slots.create_slot_proposal(title, {"start": start, "end": end, "room": room, "sub_slots": sub_slots}, groups, lecturer_ids, room, description)


# ------------------------------------------------------------- approval & actions
@tool
def approve_proposal(proposal_id: str, approver: str, edits: Optional[dict[str, Any]] = None) -> dict:
    """Approve a DRAFT proposal. ONLY call after the human explicitly approved in chat; pass their name as approver.
    edits (optional, REPLAN): {"moves": {session_id: {"date","start","room"}}, "drop": [session_id]} - re-validated for clashes."""
    p = proposals.approve_proposal(proposal_id, approver, edits)
    return {"id": p["id"], "status": p["status"], "approved_by": p["approved_by"], "approved_at": p["approved_at"], "edited": p.get("edited", False)}


@tool
def reject_proposal(proposal_id: str, reason: str) -> dict:
    """Reject a proposal with a reason."""
    p = proposals.reject_proposal(proposal_id, reason)
    return {"id": p["id"], "status": p["status"]}


@tool
def execute_proposal(proposal_id: str) -> dict:
    """Execute an APPROVED proposal: Calendar events (SUBSTITUTE: lecturer updated; RESCHEDULE/ONLINE: new slot), Gmail
    DRAFTS (substitute asked to confirm, lecturers and groups notified - never sent), change-log Doc entry, audit events.
    Refuses (NOT_APPROVED) for any other status."""
    p = proposals.execute_proposal(proposal_id, who="agent")
    return {"id": p["id"], "status": p["status"], "execution": p["execution"]}


# ------------------------------------------------------------- attendance risk (read-only)
@tool
def search_students(query: str) -> dict:
    """Find synthetic students by id, name or intake (to answer 'how many more classes can student X miss?')."""
    return attendance.list_students(None, query, 20)


@tool
def get_attendance(student_id: str) -> dict:
    """Attendance records for one (synthetic) student. Only for the student's own record or authorised staff."""
    a = attendance.get_attendance(student_id)
    a["records"] = a["records"][-40:]
    return a


@tool
def attendance_forecast(student_id: str) -> dict:
    """Current %, trend, projected % at term end, remaining sessions from the real timetable, max_more_absences
    (per module, HB §2.2) and a ready-to-use message ('you can miss at most N more classes')."""
    f = attendance.attendance_forecast(student_id)
    f.pop("weekly", None)
    return f


@tool
def attendance_risk_list(date: Optional[str] = None, limit: int = 30) -> dict:
    """Read-only ranked list of students below or heading towards the attendance threshold. Takes no actions."""
    return attendance.attendance_risk_list(date, limit)


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        import uvicorn

        uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=8001)
