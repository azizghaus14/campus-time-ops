"""M4: no action tool works without an approved proposal (R-HITL); lifecycle produces real artefacts."""
import pytest

from app.services import proposals, replan, slots, visa
from app.services.errors import Conflict, Forbidden, ToolError
from app.services.workspace import Draft, LocalWorkspace


def _draft():
    d = replan.create_disruption("LECTURER_UNAVAILABLE", {"lecturer_id": "SPG"}, {"start": "2026-11-13", "end": "2026-11-13"}, "sick")
    return replan.plan_replan(d["id"])


def test_execute_refused_for_draft():
    p = _draft()
    with pytest.raises(Forbidden) as e:
        proposals.execute_proposal(p["id"])
    assert e.value.code == "NOT_APPROVED"


def test_execute_refused_for_rejected():
    p = _draft()
    proposals.reject_proposal(p["id"], "no")
    with pytest.raises(Forbidden):
        proposals.execute_proposal(p["id"])


def test_execute_refused_for_superseded():
    p = _draft()
    replan.plan_replan(p["disruption_id"])  # re-plan supersedes v1
    with pytest.raises(Forbidden):
        proposals.execute_proposal(p["id"])


def test_approve_requires_approver_and_draft():
    p = _draft()
    with pytest.raises(ToolError):
        proposals.approve_proposal(p["id"], "")
    proposals.approve_proposal(p["id"], "PL")
    with pytest.raises(Conflict):
        proposals.approve_proposal(p["id"], "PL")


def test_send_requires_execution_and_second_confirmation(fresh_dataset):
    p = _draft()
    with pytest.raises(Forbidden):
        proposals.send_drafts(p["id"], confirm=True)
    proposals.approve_proposal(p["id"], "PL")
    proposals.execute_proposal(p["id"])
    with pytest.raises(Forbidden) as e:
        proposals.send_drafts(p["id"])
    assert e.value.code == "CONFIRMATION_REQUIRED"
    assert proposals.send_drafts(p["id"], confirm=True)["sent"] >= 1


def test_full_lifecycle_creates_artefacts_and_updates_timetable(fresh_dataset, isolated_state):
    p = _draft()
    proposals.approve_proposal(p["id"], "Programme Leader")
    done = proposals.execute_proposal(p["id"])
    ex = done["execution"]
    assert done["status"] == "EXECUTED"
    assert ex["actions"]["calendar_events"] == len(p["moves"])
    assert ex["actions"]["gmail_drafts"] >= 2
    out = isolated_state / "outbox"
    assert (out / p["id"] / "calendar_all.ics").read_text().startswith("BEGIN:VCALENDAR")
    assert list((out / p["id"] / "drafts").glob("*.eml"))
    assert "approved by" in (out / "Timetable_Change_Log.md").read_text()
    # timetable overlay applied
    m = p["moves"][0]
    s = fresh_dataset.sessions[m["session_id"]]
    assert s.start_iso() == m["to"]["start"] and s.room == m["to"]["room"]
    # audit trail
    whats = [e["what"] for e in __import__("app.services.audit", fromlist=["x"]).list_audit(p["id"])]
    assert "proposal.approved" in whats and "proposal.executed" in whats and "gmail.drafts_created" in whats


def test_edit_that_creates_clash_is_refused():
    p = _draft()
    a, b = p["moves"][0], p["moves"][1]
    with pytest.raises(ToolError) as e:
        proposals.approve_proposal(p["id"], "PL", {"moves": {b["session_id"]: {"date": a["to"]["date"], "start": a["to"]["start"][11:16], "room": a["to"]["room"]}}})
    assert e.value.code == "EDIT_CREATES_CLASH"


def test_slot_booking_and_escalation_need_approval():
    sp = slots.create_slot_proposal("Guest talk", {"start": "2026-11-18T08:30:00+08:00", "end": "2026-11-18T09:15:00+08:00", "room": "ONLINE"}, [], ["SPG"], "ONLINE")
    with pytest.raises(Forbidden):
        proposals.execute_proposal(sp["id"])
    ep = visa.plan_escalation("STU-DEMO-01")
    with pytest.raises(Forbidden):
        proposals.execute_proposal(ep["id"])
    proposals.approve_proposal(ep["id"], "International Office")
    assert proposals.execute_proposal(ep["id"])["status"] == "EXECUTED"


def test_workspace_refuses_non_demo_recipients(tmp_path):
    ws = LocalWorkspace(tmp_path)
    with pytest.raises(Forbidden):
        ws.create_drafts("x", [Draft(to=["someone@apu.edu.my"], bcc=[], subject="s", body="b")])
