"""REST API for the Ops Dashboard. Same service functions as the MCP tools."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Header, Query
from pydantic import BaseModel, Field

from .config import settings
from .data.loader import get_dataset
from .services import assistant, attendance, audit, campus, holidays, proposals, replan, rooms, shuttle, slots, substitutes, timetable
from .services.identity import Identity, can_approve, can_create_disruption, from_headers
from .services.store import get_store
from .services.policy import get_policy

router = APIRouter(prefix="/api")


def who(x_demo_role: Optional[str] = Header(None), x_demo_user: Optional[str] = Header(None)) -> Identity:
    return from_headers(x_demo_role, x_demo_user)


def _check_approve(w: Identity, proposal_id: str) -> None:
    p = proposals.get_proposal(proposal_id)
    dis = get_store().get("disruptions", p.get("disruption_id")) if p.get("disruption_id") else None
    can_approve(w, p, dis)


# ------------------------------------------------------------- models
class DisruptionIn(BaseModel):
    type: str
    scope: dict[str, Any]
    window: Optional[dict[str, str]] = None
    reason: str = ""
    created_by: str = "dashboard"


class PlanIn(BaseModel):
    options: dict[str, Any] = Field(default_factory=dict)


class ApproveIn(BaseModel):
    approver: str
    edits: Optional[dict[str, Any]] = None


class RejectIn(BaseModel):
    reason: str = ""


class SlotsIn(BaseModel):
    groups: list[Any]
    lecturer_ids: list[str] = []
    duration_min: int = 120
    window: dict[str, str]
    room_requirements: Optional[dict[str, Any]] = None
    count: int = 1
    top_n: int = 3


class SlotProposalIn(BaseModel):
    title: str
    slot: dict[str, Any]
    groups: list[Any]
    lecturer_ids: list[str] = []
    room: Optional[str] = None
    description: str = ""


# ------------------------------------------------------------- meta
@router.get("/health")
def health():
    ds = get_dataset()
    return {"ok": True, "sessions": len(ds.sessions), "data_mode": ds.meta.get("mode"), "store": settings.store_backend,
            "workspace": settings.workspace_mode, "now": settings.now().isoformat()}


@router.get("/overview")
def overview():
    ov = timetable.overview_stats()
    props = proposals.list_proposals()
    pend = [p for p in props if p["status"] == "DRAFT"]
    executed = [p for p in props if p["status"] == "EXECUTED" and p["kind"] == "REPLAN"]
    moved = sum(p.get("n_moves", 0) for p in executed)
    solve_times = sorted(p.get("stats", {}).get("total_s", 0) for p in props if p["kind"] == "REPLAN" and p.get("stats"))
    median = solve_times[len(solve_times) // 2] if solve_times else None
    # Hours saved: baseline minutes per re-planned session is a PLACEHOLDER until team interviews (docs/METRICS.md)
    baseline_min_per_session = 20
    subs = sum(p.get("summary", {}).get("substituted", 0) for p in executed)
    try:
        risk = attendance.attendance_risk_list(limit=5)
    except Exception:
        risk = {"below_threshold": None, "at_risk": None, "students": []}
    return {
        **ov,
        "disruptions_active": [d for d in replan.list_disruptions() if d.get("status") in ("OPEN", "PLANNED")][:10],
        "pending_approvals": pend[:20],
        "attendance_top": risk["students"],
        "kpis": {
            "sessions_replanned": moved,
            "substitutes_found": subs,
            "median_time_to_replan_s": median,
            "pending_approvals": len(pend),
            "students_below_threshold": risk["below_threshold"],
            "students_at_risk": risk["at_risk"],
            "proposals_executed": len(executed),
            "hours_saved_estimate": round(moved * baseline_min_per_session / 60, 1),
            "hours_saved_basis": f"{baseline_min_per_session} min manual effort per session (TBD-interview placeholder)",
        },
    }


@router.get("/policy")
def policy():
    return get_policy()


# ------------------------------------------------------------- read tools
@router.get("/lecturers/search")
def lect_search(q: str):
    return timetable.search_lecturers(q)


@router.get("/intakes/search")
def intake_search(q: str):
    return timetable.search_intakes(q)


@router.get("/lecturers/{lecturer_id}/schedule")
def lect_schedule(lecturer_id: str, start_date: str, end_date: str):
    return timetable.get_lecturer_schedule(lecturer_id, start_date, end_date)


@router.get("/groups/{intake}/schedule")
def group_schedule(intake: str, start_date: str, end_date: str, grouping: Optional[str] = None):
    return timetable.get_group_schedule(intake, grouping, start_date, end_date)


@router.get("/sessions")
def sessions_on(date: str, lecturer_id: Optional[str] = None, room: Optional[str] = None, school: Optional[str] = None,
                intake: Optional[str] = None, room_type: Optional[str] = None, after: Optional[str] = None, limit: int = 2000):
    f = {k: v for k, v in dict(lecturer_id=lecturer_id, room=room, school=school, intake=intake, room_type=room_type, after=after, limit=limit).items() if v}
    return timetable.get_sessions_on(date, f)


@router.get("/rooms")
def list_rooms():
    ds = get_dataset()
    return {"rooms": [r.to_dict() for r in sorted(ds.rooms.values(), key=lambda r: (r.type, r.name)) if r.name != "ONLINE"]}


@router.get("/rooms/free")
def free_rooms(start: str, end: str, min_capacity: int = 0, room_type: Optional[str] = None):
    return rooms.find_free_rooms(start, end, min_capacity, room_type)


@router.get("/rooms/utilisation")
def utilisation(start_date: str, end_date: str, room_type: Optional[str] = None):
    return rooms.get_room_utilisation(start_date, end_date, room_type)


@router.get("/rooms/empty-now")
def empty_now(at: Optional[str] = None):
    return rooms.empty_rooms_now(at)


@router.get("/rooms/{room}/schedule")
def room_schedule(room: str, date: str):
    return rooms.get_room_schedule(room, date)


@router.get("/holidays")
def get_holidays(year: int = 2026):
    return holidays.get_holidays(year)


@router.get("/shuttle")
def last_shuttle(date: str):
    return shuttle.get_last_shuttle(date)


@router.get("/health/timetable")
def tt_health(start_date: str, end_date: str):
    return timetable.timetable_health(start_date, end_date)


# ------------------------------------------------------------- disruptions / proposals
@router.post("/disruptions")
def create_disruption(body: DisruptionIn, x_demo_role: Optional[str] = Header(None), x_demo_user: Optional[str] = Header(None)):
    w = who(x_demo_role, x_demo_user)
    can_create_disruption(w, body.type.upper(), body.scope)
    return replan.create_disruption(body.type, body.scope, body.window, body.reason, w.label if w.role != "agent" else body.created_by)


@router.get("/disruptions")
def list_disruptions():
    return {"disruptions": replan.list_disruptions()}


@router.get("/sessions/{session_id}/substitutes")
def subs_for(session_id: str):
    return substitutes.find_substitutes(session_id)


@router.get("/disruptions/{disruption_id}")
def get_disruption(disruption_id: str, limit: int = Query(2000, le=5000)):
    return replan.get_disruption(disruption_id, True, limit)


@router.post("/disruptions/{disruption_id}/plan")
def plan(disruption_id: str, body: PlanIn = Body(default=PlanIn()), x_demo_role: Optional[str] = Header(None), x_demo_user: Optional[str] = Header(None)):
    w = who(x_demo_role, x_demo_user)
    dis = replan.get_disruption(disruption_id, with_sessions=False)
    can_create_disruption(w, dis["type"], dis["scope"])
    return replan.plan_replan(disruption_id, body.options, created_by=w.label if w.role != "agent" else "dashboard")


@router.get("/proposals")
def list_props(status: Optional[str] = None, kind: Optional[str] = None):
    return {"proposals": proposals.list_proposals(status, kind)}


@router.get("/proposals/{proposal_id}")
def get_prop(proposal_id: str):
    return proposals.get_proposal(proposal_id)


@router.get("/proposals/{proposal_id}/explain")
def explain(proposal_id: str):
    return replan.explain_proposal(proposal_id)


@router.post("/proposals/{proposal_id}/approve")
def approve(proposal_id: str, body: ApproveIn, x_demo_role: Optional[str] = Header(None), x_demo_user: Optional[str] = Header(None)):
    w = who(x_demo_role, x_demo_user)
    _check_approve(w, proposal_id)
    return proposals.approve_proposal(proposal_id, w.label if w.role != "agent" else body.approver, body.edits)


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: str, body: RejectIn, x_demo_role: Optional[str] = Header(None), x_demo_user: Optional[str] = Header(None)):
    w = who(x_demo_role, x_demo_user)
    _check_approve(w, proposal_id)
    return proposals.reject_proposal(proposal_id, body.reason, who=w.label)


@router.post("/proposals/{proposal_id}/execute")
def execute(proposal_id: str, x_demo_role: Optional[str] = Header(None), x_demo_user: Optional[str] = Header(None)):
    w = who(x_demo_role, x_demo_user)
    _check_approve(w, proposal_id)
    return proposals.execute_proposal(proposal_id, who=w.label if w.role != "agent" else "dashboard")


@router.get("/audit")
def audit_log(proposal_id: Optional[str] = None, limit: int = 500):
    return {"events": audit.list_audit(proposal_id, limit)}


# ------------------------------------------------------------- slot finder
@router.post("/slots/find")
def find_slots(body: SlotsIn):
    return slots.find_common_slots(body.groups, body.lecturer_ids, body.duration_min, body.window, body.room_requirements, body.count, body.top_n)


@router.post("/slots/propose")
def propose_slot(body: SlotProposalIn):
    return slots.create_slot_proposal(body.title, body.slot, body.groups, body.lecturer_ids, body.room, body.description, created_by="dashboard")


# ------------------------------------------------------------- attendance risk (read-only)
def _staff_only(w: Identity) -> None:
    if w.role == "student":
        from .services.errors import Forbidden

        raise Forbidden("ROLE_FORBIDDEN", "Students can only see their own attendance.")


def _own_or_staff(w: Identity, student_id: str) -> None:
    if w.role == "student" and student_id.upper() != (w.user or ""):
        from .services.errors import Forbidden

        raise Forbidden("ROLE_FORBIDDEN", "Students can only see their own attendance.")


@router.get("/attendance/students")
def students(intake: Optional[str] = None, q: Optional[str] = None, limit: int = 200,
             x_demo_role: Optional[str] = Header(None), x_demo_user: Optional[str] = Header(None)):
    _staff_only(who(x_demo_role, x_demo_user))
    return attendance.list_students(intake, q, limit)


@router.get("/attendance/risk")
def risk(limit: int = 100, x_demo_role: Optional[str] = Header(None), x_demo_user: Optional[str] = Header(None)):
    _staff_only(who(x_demo_role, x_demo_user))
    return attendance.attendance_risk_list(None, limit)


@router.get("/attendance/students/{student_id}")
def student(student_id: str, x_demo_role: Optional[str] = Header(None), x_demo_user: Optional[str] = Header(None)):
    _own_or_staff(who(x_demo_role, x_demo_user), student_id)
    rec = attendance.get_student_record(student_id)
    return {"student": {k: rec[k] for k in ("id", "name", "intake", "grouping")}, "forecast": attendance.attendance_forecast(student_id)}


@router.get("/attendance/students/{student_id}/records")
def records(student_id: str, x_demo_role: Optional[str] = Header(None), x_demo_user: Optional[str] = Header(None)):
    _own_or_staff(who(x_demo_role, x_demo_user), student_id)
    return attendance.get_attendance(student_id)


# ------------------------------------------------------------- assistant + personas + campus + me
class ChatIn(BaseModel):
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


@router.post("/assistant")
def chat(body: ChatIn, x_demo_role: Optional[str] = Header(None), x_demo_user: Optional[str] = Header(None)):
    w = who(x_demo_role, x_demo_user)
    out = assistant.handle(body.message, w if w.role != "agent" else Identity("admin"), body.context)
    out["engine"] = assistant.engine_name()
    return out


@router.get("/assistant/suggestions")
def chat_suggestions(x_demo_role: Optional[str] = Header(None), x_demo_user: Optional[str] = Header(None)):
    return {"suggestions": assistant.suggestions(who(x_demo_role, x_demo_user)), "engine": assistant.engine_name()}


@router.get("/personas")
def personas():
    ds = get_dataset()
    lect = ["MZD", "SPG", "CMM", "RVK", "SCY"]
    stud = ["STU-DEMO-01", "STU-DEMO-02", "STU-DEMO-03", "STU-DEMO-04"]
    return {
        "admin": [{"id": "ADMIN", "name": "Timetabling Office", "subtitle": "Full campus operations"}],
        "lecturer": [{"id": l, "name": ds.lecturer_names[l], "subtitle": ", ".join(sorted({ds.sessions[i].module_name for i in ds.by_lecturer[l]})[:2])}
                     for l in lect if l in ds.by_lecturer],
        "student": [{"id": s, "name": attendance.get_student_record(s)["name"],
                     "subtitle": f"{attendance.get_student_record(s)['intake']} / {attendance.get_student_record(s)['grouping']}"} for s in stud],
    }


@router.get("/campus/layout")
def campus_layout():
    return campus.layout()


@router.get("/campus/day")
def campus_day(date: str):
    return campus.day(date)


@router.get("/me")
def me(x_demo_role: Optional[str] = Header(None), x_demo_user: Optional[str] = Header(None)):
    from datetime import timedelta

    from .config import settings

    w = who(x_demo_role, x_demo_user)
    today = settings.now().date()
    out: dict[str, Any] = {"role": w.role, "user": w.user, "label": w.label, "now": settings.now().isoformat()}
    if w.role == "lecturer" and w.user:
        sched = timetable.get_lecturer_schedule(w.user, today.isoformat(), (today + timedelta(days=13)).isoformat())
        mine = [p for p in proposals.list_proposals(compact=True) if p.get("disruption_id")
                and (get_store().get("disruptions", p["disruption_id"]) or {}).get("scope", {}).get("lecturer_id") == w.user]
        out.update({"name": get_dataset().lecturer_names.get(w.user), "schedule": sched["sessions"], "proposals": mine[:10]})
    elif w.role == "student" and w.user:
        st = attendance.get_student_record(w.user)
        sched = timetable.get_group_schedule(st["intake"], st["grouping"], today.isoformat(), (today + timedelta(days=13)).isoformat())
        f = attendance.attendance_forecast(w.user)
        f.pop("weekly_detail", None)
        out.update({"name": st["name"], "intake": st["intake"], "grouping": st["grouping"], "schedule": sched["sessions"],
                    "changes": [s for s in sched["sessions"] if s.get("moved_by")], "attendance": f})
    return out
