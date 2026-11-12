"""REST API for the Ops Dashboard. Same service functions as the MCP tools."""
from __future__ import annotations

import base64
from typing import Any, Optional

from fastapi import APIRouter, Body, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from .config import settings
from .data.loader import get_dataset
from .services import audit, holidays, mrz, proposals, replan, rooms, shuttle, slots, timetable, visa
from .services.policy import get_policy

router = APIRouter(prefix="/api")


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


class SendIn(BaseModel):
    confirm: bool = False


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


class PassportIn(BaseModel):
    image_base64: Optional[str] = None
    mrz_text: Optional[str] = None
    student_id: Optional[str] = None


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
    try:
        risk = visa.visa_risk_sweep(limit=5)
        at_risk = risk["at_risk"]
        top_risk = risk["students"]
    except Exception:
        at_risk, top_risk = None, []
    return {
        **ov,
        "disruptions_active": [d for d in replan.list_disruptions() if d.get("status") in ("OPEN", "PLANNED")][:10],
        "pending_approvals": pend[:20],
        "pending_count": len(pend),
        "visa_at_risk": at_risk,
        "visa_top": top_risk,
        "kpis": {
            "sessions_replanned": moved,
            "proposals_executed": len(executed),
            "median_time_to_replan_s": median,
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
def create_disruption(body: DisruptionIn):
    return replan.create_disruption(body.type, body.scope, body.window, body.reason, body.created_by)


@router.get("/disruptions")
def list_disruptions():
    return {"disruptions": replan.list_disruptions()}


@router.get("/disruptions/{disruption_id}")
def get_disruption(disruption_id: str, limit: int = Query(2000, le=5000)):
    return replan.get_disruption(disruption_id, True, limit)


@router.post("/disruptions/{disruption_id}/plan")
def plan(disruption_id: str, body: PlanIn = Body(default=PlanIn())):
    return replan.plan_replan(disruption_id, body.options, created_by="dashboard")


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
def approve(proposal_id: str, body: ApproveIn):
    return proposals.approve_proposal(proposal_id, body.approver, body.edits)


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: str, body: RejectIn):
    return proposals.reject_proposal(proposal_id, body.reason, who="dashboard")


@router.post("/proposals/{proposal_id}/execute")
def execute(proposal_id: str):
    return proposals.execute_proposal(proposal_id, who="dashboard")


@router.post("/proposals/{proposal_id}/send")
def send(proposal_id: str, body: SendIn):
    return proposals.send_drafts(proposal_id, body.confirm, who="dashboard")


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


# ------------------------------------------------------------- visa guardian
@router.get("/visa/students")
def students(international_only: bool = False, intake: Optional[str] = None, q: Optional[str] = None, limit: int = 200):
    return visa.list_students(international_only, intake, q, limit)


@router.get("/visa/sweep")
def sweep(limit: int = 100):
    return visa.visa_risk_sweep(None, limit)


@router.post("/visa/daily-sweep")
def daily(max_students: int = 25):
    return visa.daily_sweep(max_students)


@router.get("/visa/students/{student_id}")
def student(student_id: str):
    rec = visa.get_student_record(student_id)
    f = visa.attendance_forecast(student_id)
    lad = visa._ladder_state(student_id)
    props = [p for p in proposals.list_proposals(kind="ESCALATION", compact=False) if p.get("student_id") == student_id]
    return {"student": {k: v for k, v in rec.items() if k != "absences"}, "forecast": f, "ladder": lad, "escalations": props}


@router.get("/visa/students/{student_id}/attendance")
def attendance(student_id: str):
    return visa.get_attendance(student_id)


@router.post("/visa/students/{student_id}/escalate")
def escalate(student_id: str, step: Optional[str] = None):
    return visa.plan_escalation(student_id, step, created_by="dashboard")


@router.post("/visa/passport")
def passport_json(body: PassportIn):
    return mrz.parse_passport_image(body.image_base64, body.mrz_text, body.student_id)


@router.post("/visa/passport/upload")
async def passport_upload(file: UploadFile = File(...), student_id: Optional[str] = Form(None)):
    raw = await file.read()
    return mrz.parse_passport_image(student_id=student_id, image_bytes=raw)


@router.get("/visa/demo-passports")
def demo_passports():
    import json

    p = settings.data_dir / "demo_passports" / "manifest.json"
    items = json.loads(p.read_text()) if p.exists() else []
    for i in items:
        i["url"] = f"{settings.public_base_url}/demo-passports/{i['file']}"
    return {"passports": items}
