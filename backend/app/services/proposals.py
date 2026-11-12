"""Proposal lifecycle shared by Replan and Slot Finder.

DRAFT --approve--> APPROVED --execute--> EXECUTED
  \\--reject--> REJECTED        DRAFT --(re-plan)--> SUPERSEDED

R-HITL: every side effect (calendar event, Gmail draft, change-log entry) lives in execute_* and refuses anything that is
not APPROVED. The system only ever creates Gmail DRAFTS; a human sends them from Gmail.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Optional

from ..config import settings
from ..data.loader import get_dataset
from ..domain import ProposalKind, ProposalStatus, hhmm, iso, parse_iso
from ..solver.model import Cand, check_no_clashes
from .audit import log_event
from .errors import Conflict, Forbidden, NotFound, ToolError, require
from .store import get_store
from .workspace import CalendarEvent, Draft, addr_intake, addr_lecturer, addr_role, get_workspace, new_uid


def get_proposal(proposal_id: str) -> dict:
    p = get_store().get("proposals", proposal_id)
    if not p:
        raise NotFound("UNKNOWN_PROPOSAL", f"No proposal {proposal_id}")
    return p


def list_proposals(status: Optional[str] = None, kind: Optional[str] = None, compact: bool = True) -> list[dict]:
    items = get_store().list("proposals")
    if status:
        items = [p for p in items if p["status"] == status.upper()]
    if kind:
        items = [p for p in items if p["kind"] == kind.upper()]
    items.sort(key=lambda p: p["id"], reverse=True)
    if compact:
        keep = ("id", "kind", "title", "status", "version", "created_at", "created_by", "disruption_id", "disruption_type",
                "summary", "stats", "approved_by", "approved_at", "executed_at", "bulk")
        out = []
        for p in items:
            c = {k: p[k] for k in keep if k in p}
            c["n_moves"] = len(p.get("moves", []))
            c["n_unresolved"] = len(p.get("unresolved", []))
            if c.get("summary"):
                c["summary"] = {k: v for k, v in c["summary"].items() if k not in ("by_school", "clash_check", "candidate_days")}
            out.append(c)
        return out
    return items


def approve_proposal(proposal_id: str, approver: str, edits: Optional[dict] = None) -> dict:
    st = get_store()
    p = get_proposal(proposal_id)
    require(bool(approver and approver.strip()), "APPROVER_REQUIRED", "approver is required (who is approving?)")
    if p["status"] != ProposalStatus.DRAFT.value:
        raise Conflict("NOT_DRAFT", f"Proposal {proposal_id} is {p['status']}; only DRAFT proposals can be approved")
    before = {"status": p["status"]}
    if edits:
        _apply_edits(p, edits)
    p["status"] = ProposalStatus.APPROVED.value
    p["approved_by"] = approver.strip()
    p["approved_at"] = settings.now().isoformat()
    st.put("proposals", proposal_id, p)
    log_event(approver, "proposal.approved", proposal_id, before=before, after={"status": "APPROVED", "edits": edits or None})
    return p


def _apply_edits(p: dict, edits: dict) -> None:
    """Manual edits by the approver: {"moves": {session_id: {"date","start","room"}}, "drop": [session_id]}.
    Re-validated with the independent clash checker before approval."""
    require(p["kind"] == ProposalKind.REPLAN.value, "EDITS_UNSUPPORTED", "edits are supported on REPLAN proposals; re-plan for others")
    ds = get_dataset()
    by_sid = {m["session_id"]: m for m in p["moves"]}
    for sid in edits.get("drop", []) or []:
        if sid in by_sid:
            m = by_sid.pop(sid)
            p["unresolved"].append({"session": {"id": sid, "module_name": m["module_name"], "date": m["from"]["date"], "time": m["from"]["label"]},
                                    "reason": "dropped by approver (to be cancelled or handled manually)", "options": [], "rule_ids": ["R-UNRESOLVED"]})
    for sid, ch in (edits.get("moves") or {}).items():
        require(sid in by_sid, "UNKNOWN_MOVE", f"session {sid} is not in this proposal")
        m = by_sid[sid]
        s = ds.sessions[sid]
        d = date.fromisoformat(ch.get("date", m["to"]["date"]))
        start = ch.get("start")
        smin = (int(start.split(":")[0]) * 60 + int(start.split(":")[1])) if start else parse_iso(m["to"]["start"]).hour * 60 + parse_iso(m["to"]["start"]).minute
        room = ch.get("room", m["to"]["room"])
        require(room in ds.rooms, "UNKNOWN_ROOM", f"No room {room}")
        m["to"] = {"date": d.isoformat(), "start": iso(d, smin), "end": iso(d, smin + s.duration), "room": room,
                   "online": room == "ONLINE", "label": f"{d.strftime('%a %d %b')} {hhmm(smin)}-{hhmm(smin + s.duration)}"}
        m["rationale"] = "Manually edited by approver; re-validated by clash check. " + m["rationale"]
    cands = {}
    for sid, m in by_sid.items():
        st_ = parse_iso(m["to"]["start"])
        en_ = parse_iso(m["to"]["end"])
        cands[sid] = Cand(sid, st_.date(), st_.hour * 60 + st_.minute, en_.hour * 60 + en_.minute, m["to"]["room"], m["to"]["online"], 0, [])
    problems = check_no_clashes(ds, cands, p.get("substitutes") or {})
    if problems:
        raise ToolError("EDIT_CREATES_CLASH", "The edit would create a clash; not approved", problems=problems[:10])
    p["moves"] = sorted(by_sid.values(), key=lambda m: (m["from"]["start"], m["session_id"]))
    p["edited"] = True


def reject_proposal(proposal_id: str, reason: str, who: str = "approver") -> dict:
    st = get_store()
    p = get_proposal(proposal_id)
    if p["status"] not in (ProposalStatus.DRAFT.value, ProposalStatus.APPROVED.value, "INVALID"):
        raise Conflict("CANNOT_REJECT", f"Proposal is {p['status']}")
    before = p["status"]
    p["status"] = ProposalStatus.REJECTED.value
    p["rejected_reason"] = reason or ""
    p["rejected_at"] = settings.now().isoformat()
    st.put("proposals", proposal_id, p)
    log_event(who, "proposal.rejected", proposal_id, before={"status": before}, after={"status": "REJECTED", "reason": reason})
    return p


def _require_approved(p: dict) -> None:
    if p["status"] != ProposalStatus.APPROVED.value:
        raise Forbidden(
            "NOT_APPROVED",
            f"Proposal {p['id']} is {p['status']}. Actions require an APPROVED proposal (R-HITL).",
            proposal_id=p["id"], status=p["status"],
        )


def execute_proposal(proposal_id: str, who: str = "system") -> dict:
    p = get_proposal(proposal_id)
    _require_approved(p)
    kind = p["kind"]
    if kind == ProposalKind.REPLAN.value:
        result = _execute_replan(p, who)
    elif kind == ProposalKind.SLOT_BOOKING.value:
        from .slots import execute_slot_booking

        result = execute_slot_booking(p, who)
    else:
        raise ToolError("BAD_KIND", f"unknown proposal kind {kind}")
    p = get_proposal(proposal_id)
    p["status"] = ProposalStatus.EXECUTED.value
    p["executed_at"] = settings.now().isoformat()
    p["executed_by"] = who
    p["execution"] = result
    get_store().put("proposals", proposal_id, p)
    log_event(who, "proposal.executed", proposal_id, before={"status": "APPROVED"}, after={"status": "EXECUTED", "actions": result.get("actions")})
    return p


def _execute_replan(p: dict, who: str) -> dict:
    from .holidays import declare_runtime_holiday
    from .replan import apply_moves_to_dataset

    ds = get_dataset()
    ws = get_workspace()
    st = get_store()
    moves = p["moves"]
    ref = p["id"]

    events = []
    for m in moves:
        att = [addr_lecturer(m.get("substitute") or m["lecturer_id"])] + [addr_intake(g["intake"], g["grouping"]) for g in m["affected_groups"]]
        if m["type"] == "SUBSTITUTE":
            summary = f"[SUBSTITUTE] {m['module_name']} - taught by {m['substitute']} (was {m['lecturer_id']})"
            what = f"Same time and room ({m['from']['label']} {m['from']['room']}); lecturer changed to {m['substitute_name']} ({m['substitute']})."
        else:
            summary = f"[{'ONLINE' if m['type'] == 'ONLINE' else 'RESCHEDULED'}] {m['module_name']} ({m['lecturer_id']})"
            what = f"Moved from {m['from']['label']} {m['from']['room']} to {m['to']['label']} {m['to']['room']}."
        events.append(CalendarEvent(
            summary=summary, start=m["to"]["start"], end=m["to"]["end"],
            location=("Online (link to follow)" if m["to"]["room"] == "ONLINE" else m["to"]["room"]),
            description=(f"{what}\nReason: {p['title']}.\nWhy: {m['rationale']}\nRules: {', '.join(m['rule_ids'])}\n"
                         f"Approved by {p.get('approved_by')} - proposal {ref}."),
            attendees=att, uid=new_uid(m["session_id"]),
        ))
    cal = ws.create_events(ref, events)

    drafts = _replan_drafts(p)
    dr = ws.create_drafts(ref, drafts)

    md = [f"**Proposal:** {ref} v{p['version']} - **approved by** {p.get('approved_by')} at {p.get('approved_at')}  ",
          f"**Disruption:** {p.get('disruption_id')} ({p.get('disruption_type')})  ",
          f"**Result:** {p['summary'].get('substituted', 0)} substitute(s), {p['summary'].get('rescheduled', 0)} rescheduled, "
          f"{p['summary'].get('placed_online', 0)} online, {len(p['unresolved'])} unresolved. Clash check passed.", "",
          "| Type | Module | Lecturer | From | To | Groups | Rules |", "|---|---|---|---|---|---|---|"]
    for m in moves[:400]:
        to = f"same slot, {m['substitute']} teaches" if m["type"] == "SUBSTITUTE" else f"{m['to']['label']} {m['to']['room']}"
        md.append(f"| {m['type']} | {m['module_name']} | {m['lecturer_id']} | {m['from']['label']} {m['from']['room']} | {to} | "
                  f"{len(m['affected_groups'])} | {', '.join(m['rule_ids'][:4])} |")
    if len(moves) > 400:
        md.append(f"| | ... {len(moves) - 400} more (see dashboard) | | | | | |")
    for u in p["unresolved"]:
        md.append(f"\n- UNRESOLVED: {u['session'].get('module_name')} {u['session'].get('date')} - {u['reason']}")
    log = ws.append_changelog(ref, f"{settings.now().strftime('%d %b %Y %H:%M')} - {p['title']}", "\n".join(md))

    apply_moves_to_dataset(ds, moves, ref)
    dis = st.get("disruptions", p.get("disruption_id")) if p.get("disruption_id") else None
    if dis:
        dis["status"] = "EXECUTED"
        st.put("disruptions", dis["id"], dis)
        if dis["type"] == "HOLIDAY":
            declare_runtime_holiday(date.fromisoformat(dis["scope"]["date"]), dis["scope"].get("name", "Declared holiday"), dis["id"])
    for kind, n in (("calendar.events_created", cal["count"]), ("gmail.drafts_created", dr["count"]), ("docs.changelog_appended", 1)):
        log_event(who, kind, ref, after={"count": n, "mode": ws.mode})
    log_event(who, "timetable.updated", ref,
              before=[{"session": m["session_id"], **{k: m["from"][k] for k in ("start", "room")}} for m in moves[:200]],
              after=[{"session": m["session_id"], **{k: m["to"][k] for k in ("start", "room")}} for m in moves[:200]])
    return {
        "mode": ws.mode,
        "actions": {"calendar_events": cal["count"], "gmail_drafts": dr["count"], "changelog_entries": 1, "audit_events": 5},
        "calendar": {**cal, "events": cal["events"][:30]},
        "drafts": {**dr, "drafts": dr["drafts"][:30]},
        "draft_ids": [d["id"] for d in dr["drafts"]],
        "changelog": log,
    }


def _replan_drafts(p: dict) -> list[Draft]:
    moves = p["moves"]
    by_lect: dict[str, list] = defaultdict(list)
    by_intake: dict[str, list] = defaultdict(list)
    subs: dict[str, list] = defaultdict(list)
    for m in moves:
        if m["type"] == "SUBSTITUTE":
            subs[m["substitute"]].append(m)
        else:
            by_lect[m["lecturer_id"]].append(m)
        for g in m["affected_groups"]:
            by_intake[g["intake"]].append((g["grouping"], m))
    drafts = []
    footer = ("\n\nThis change was planned by Campus Time Ops and approved by a member of staff. "
              "If the new time does not work for you, reply to this email and the timetabling office will help.\n")
    for lid, ms in sorted(subs.items()):
        lines = [f"- {m['module_name']} ({', '.join(m['module_ids'][:2])}): {m['from']['label']} in {m['from']['room']}, "
                 f"{len(m['affected_groups'])} group(s), ~{m['students']} students" for m in ms]
        drafts.append(Draft(to=[addr_lecturer(lid)], bcc=[], subject=f"Please confirm: cover {len(ms)} session(s) for {ms[0]['lecturer_id']}",
                            body=(f"Dear colleague,\n\n{ms[0]['lecturer_name']} is unavailable. You teach the same module, are free at these "
                                  f"times and stay within the daily load limit, so we would like to ask you to cover:\n\n" + "\n".join(lines)
                                  + "\n\nPlease reply YES to confirm or NO if you cannot cover; the timetabling office will then reschedule." + footer)))
    for lid, ms in sorted(by_lect.items()):
        lines = [f"- {m['module_name']}: {m['from']['label']} {m['from']['room']}  ->  {m['to']['label']} {m['to']['room']}" for m in ms]
        drafts.append(Draft(to=[addr_lecturer(lid)], bcc=[], subject=f"Timetable change: {len(ms)} session(s) - {p['title']}",
                            body=f"Dear colleague,\n\nYour sessions have been re-planned ({p['title']}):\n\n" + "\n".join(lines) + footer))
    if len(by_intake) <= 60:
        for intake, gm in sorted(by_intake.items()):
            lines = sorted({(f"- {m['module_name']} ({g}): {m['from']['label']} in {m['from']['room']} goes ahead as planned, "
                             f"taught by {m['substitute_name']}") if m["type"] == "SUBSTITUTE" else
                            f"- {m['module_name']} ({g}): {m['from']['label']}  ->  {m['to']['label']} in {m['to']['room']}" for g, m in gm})
            only_sub = all(m["type"] == "SUBSTITUTE" for _, m in gm)
            drafts.append(Draft(to=[addr_intake(intake)], bcc=[],
                                subject=f"[{intake}] {'Lecturer change' if only_sub else 'Class rescheduled'} - {p['title']}",
                                body=f"Dear students of {intake},\n\nPlease note the following change(s):\n\n" + "\n".join(lines)
                                     + "\n\nYour calendar has been updated." + footer))
    else:
        by_school: dict[str, set] = defaultdict(set)
        for m in moves:
            for g in m["affected_groups"]:
                by_school[m["school"]].add(g["intake"])
        for school, intakes in sorted(by_school.items()):
            il = sorted(intakes)
            for i in range(0, len(il), 50):
                chunk = il[i:i + 50]
                drafts.append(Draft(to=[addr_role(f"announcements-{school.lower()}")], bcc=[addr_intake(x) for x in chunk],
                                    subject=f"[{school}] Classes rescheduled - {p['title']}",
                                    body=(f"Dear students,\n\n{p['title']}. All affected classes for your intake have been moved. "
                                          "Your personal calendar has been updated with the new times and rooms; please check APSpace / your calendar." + footer)))
    return drafts
