"""ADK fallback (BUILD_PROMPT §3): the same two agents implemented with Google ADK + Gemini on Vertex AI, consuming the
same Campus MCP server. Use only if the Gemini Enterprise tenant cannot call a custom MCP server (docs/DECISIONS.md D-02).

    pip install google-adk
    export GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=<project> GOOGLE_CLOUD_LOCATION=asia-southeast1
    export CAMPUS_MCP_URL=https://<backend>/mcp MCP_AUTH_TOKEN=<token>
    adk web agents            # dev UI; or `adk deploy agent_engine agents/adk_app` for Vertex AI Agent Engine

Approval is enforced twice: ADK asks the user to confirm approve/execute tool calls (require_confirmation), and the
MCP server refuses any action whose proposal is not APPROVED.
"""
from __future__ import annotations

import os
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

HERE = Path(__file__).resolve().parent
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")
MCP_URL = os.environ.get("CAMPUS_MCP_URL", "http://localhost:8000/mcp")
HEADERS = {"Authorization": f"Bearer {os.environ['MCP_AUTH_TOKEN']}"} if os.environ.get("MCP_AUTH_TOKEN") else {}

ACTION_TOOLS = ["approve_proposal", "execute_proposal"]


def _toolsets(read_and_plan: list[str]) -> list[McpToolset]:
    conn = StreamableHTTPConnectionParams(url=MCP_URL, headers=HEADERS, timeout=30)
    return [
        McpToolset(connection_params=conn, tool_filter=read_and_plan),
        McpToolset(connection_params=conn, tool_filter=ACTION_TOOLS, require_confirmation=True),
    ]


def _instructions(name: str) -> str:
    return (HERE.parent / name / "instructions.md").read_text()


replan_agent = LlmAgent(
    name="replan",
    model=MODEL,
    description="Re-plans the timetable for sick lecturers, closed rooms and declared holidays; answers attendance questions.",
    instruction=_instructions("replan"),
    tools=_toolsets([
        "search_lecturers", "search_intakes", "get_lecturer_schedule", "get_group_schedule", "get_room_schedule",
        "get_sessions_on", "find_free_rooms", "get_holidays", "get_last_shuttle", "get_policy", "create_disruption",
        "find_substitutes", "plan_replan", "explain_proposal", "get_proposal", "list_proposals", "reject_proposal",
        "search_students", "attendance_forecast", "get_attendance",
    ]),
)

slot_finder_agent = LlmAgent(
    name="slot_finder",
    model=MODEL,
    description="Finds common free slots for groups, examiners and rooms, and drafts bookings.",
    instruction=_instructions("slot_finder"),
    tools=_toolsets([
        "search_lecturers", "search_intakes", "get_group_schedule", "get_lecturer_schedule", "find_free_rooms",
        "get_holidays", "find_common_slots", "create_slot_proposal", "get_proposal", "reject_proposal",
    ]),
)

# Router: one entry point that hands off to the right specialist.
root_agent = LlmAgent(
    name="campus_time_ops",
    model=MODEL,
    description="Campus Time Ops front door.",
    instruction=(
        "Route the user: disruptions (sick lecturer, closed room, holiday) and attendance questions -> replan; "
        "finding slots for vivas, presentations, events or make-up classes -> slot_finder. Do not answer yourself."
    ),
    sub_agents=[replan_agent, slot_finder_agent],
)
