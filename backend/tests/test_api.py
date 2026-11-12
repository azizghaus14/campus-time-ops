"""REST + MCP surface: endpoints respond, MCP requires bearer token, MCP exposes all tools."""
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    os.environ["MCP_AUTH_TOKEN"] = "t0k"
    from app.config import settings

    settings.mcp_auth_token = "t0k"
    from app.main import app

    with TestClient(app) as c:
        yield c


H = {"content-type": "application/json", "accept": "application/json, text/event-stream"}


def test_health_and_overview(client):
    assert client.get("/api/health").json()["ok"]
    ov = client.get("/api/overview").json()
    assert ov["physical_sessions"] > 1000 and "kpis" in ov


def test_read_endpoints(client):
    assert client.get("/api/sessions", params={"date": "2026-11-16"}).json()["count"] > 300
    assert client.get("/api/shuttle", params={"date": "2026-11-17"}).json()["latest_class_end"] == "19:00"
    assert client.get("/api/holidays").json()["count"] > 20
    u = client.get("/api/rooms/utilisation", params={"start_date": "2026-11-16", "end_date": "2026-11-20"}).json()
    assert len(u["hours"]) == 13 and u["rooms"]
    assert client.get("/api/lecturers/ZZZZ/schedule", params={"start_date": "2026-11-12", "end_date": "2026-11-13"}).status_code == 404


def test_structured_validation_errors(client):
    r = client.post("/api/disruptions", json={"type": "NOPE", "scope": {}})
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_TYPE"


def test_execute_without_approval_is_403(client):
    d = client.post("/api/disruptions", json={"type": "LECTURER_UNAVAILABLE", "scope": {"lecturer_id": "SPG"}, "window": {"start": "2026-11-13", "end": "2026-11-13"}}).json()
    p = client.post(f"/api/disruptions/{d['id']}/plan", json={"options": {}}).json()
    r = client.post(f"/api/proposals/{p['id']}/execute")
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_APPROVED"


def test_mcp_requires_token_and_lists_tools(client):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    assert client.post("/mcp", json=body, headers=H).status_code == 401
    r = client.post("/mcp", json=body, headers={**H, "Authorization": "Bearer t0k"})
    names = {t["name"] for t in r.json()["result"]["tools"]}
    for required in ["get_lecturer_schedule", "create_disruption", "plan_replan", "approve_proposal", "execute_proposal",
                     "find_common_slots", "attendance_forecast", "visa_risk_sweep", "parse_passport_image", "plan_escalation"]:
        assert required in names


def test_mcp_action_tool_refuses_unapproved(client):
    body = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "execute_proposal", "arguments": {"proposal_id": "PRO-9999"}}}
    r = client.post("/mcp", json=body, headers={**H, "Authorization": "Bearer t0k"}).json()
    assert "UNKNOWN_PROPOSAL" in r["result"]["content"][0]["text"]
