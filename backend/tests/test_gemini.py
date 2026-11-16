"""Gemini fallback: only for messages the rules don't recognise, read-only tools scoped by role, safe fallback on failure."""
import json

import pytest

from app.services import gemini
from app.services.assistant import handle
from app.services.identity import Identity

L, A, S = Identity("lecturer", "MZD"), Identity("admin"), Identity("student", "STU-DEMO-01")
WRITE_TOOLS = {"create_disruption", "plan_replan", "approve_proposal", "execute_proposal", "reject_proposal", "create_slot_proposal"}


class Fake:
    """Scripted Gemini: replies in turn; records every request body."""

    def __init__(self, *replies):
        self.replies, self.bodies = list(replies), []

    def __call__(self, url, headers=None, data=None, timeout=None):
        self.bodies.append(json.loads(data))
        r = self.replies.pop(0)

        class R:
            status_code = r.get("status", 200)
            text = "err"

            def json(self_inner):
                return {"candidates": [{"content": {"role": "model", "parts": r["parts"]}}]}

        return R()


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("CHAT_GEMINI", "on")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


def test_off_without_key(monkeypatch):
    monkeypatch.setenv("CHAT_GEMINI", "on")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert not gemini.enabled()
    assert handle("which day this week is my longest?", S).get("engine") is None


def test_unrecognised_message_goes_to_gemini_with_tool_call(on, monkeypatch):
    fake = Fake({"parts": [{"functionCall": {"name": "my_timetable", "args": {"start_date": "2026-11-12", "end_date": "2026-11-13"}}}]},
                {"parts": [{"text": "Your longest day is **Tuesday**."}]})
    monkeypatch.setattr(gemini.requests, "post", fake)
    r = handle("which day next week is my longest?", S)
    assert r["engine"] == "gemini" and "Tuesday" in r["reply"] and r["tools_used"] == ["my_timetable"]
    assert r["cards"] and r["cards"][0]["type"] == "schedule"
    sent = fake.bodies[1]["contents"][-1]["parts"][0]["functionResponse"]
    assert sent["name"] == "my_timetable" and "sessions" in sent["response"]["result"]


def test_core_flows_never_touch_gemini(on, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("Gemini must not be called for core flows")
    monkeypatch.setattr(gemini.requests, "post", boom)
    assert handle("How many more classes can I miss?", S)["cards"][0]["type"] == "attendance"
    assert handle("I'm sick tomorrow, sort out my classes", L)["cards"][1]["type"] == "proposal"


def test_tools_are_read_only_and_scoped_by_role():
    for who in (S, L, A):
        names = set(gemini._tools(who))
        assert not names & WRITE_TOOLS
    s = set(gemini._tools(S))
    assert {"my_timetable", "my_attendance"} <= s
    assert not s & {"get_lecturer_schedule", "get_group_schedule", "attendance_forecast", "attendance_risk_list"}
    assert "attendance_forecast" not in gemini._tools(L) and "attendance_forecast" in gemini._tools(A)


def test_failure_falls_back_to_help(on, monkeypatch):
    monkeypatch.setattr(gemini.requests, "post", Fake({"status": 429, "parts": []}))
    r = handle("which day next week is my longest?", S)
    assert r.get("engine") is None and "how many more classes you can miss" in r["reply"]


def test_gemini_enterprise_connector_cannot_approve_or_execute():
    from app.mcp_server import GEMINI_TOOLS
    names = {f.__name__ for f in GEMINI_TOOLS}
    assert not names & {"approve_proposal", "execute_proposal", "reject_proposal", "create_slot_proposal"}
    assert {"plan_replan", "create_disruption", "get_lecturer_schedule"} <= names


def test_planning_tool_only_in_agent_mode_and_never_approves():
    assert "draft_replan" in gemini._tools(A, planning=True)
    assert "draft_replan" not in gemini._tools(A) and "draft_replan" not in gemini._tools(S, planning=False)
    r = gemini._draft_replan("LECTURER_UNAVAILABLE", lecturer_id="MZD", start_date="2026-11-13", end_date="2026-11-13", reason="sick")
    assert r["status"] == "DRAFT" and r["proposal_id"]
