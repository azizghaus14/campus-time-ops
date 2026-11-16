"""A2A (Agent2Agent) endpoint so Gemini Enterprise can use Campus Time Ops as a registered custom agent.

Gemini Enterprise -> POST /g/<MCP_PUBLIC_SECRET>/a2a  (JSON-RPC 2.0, method "message/send")
                  <- an agent Message whose text was produced by Gemini using our tools (services/gemini.py, planning mode).
The agent can look things up and DRAFT re-plans; it cannot approve or execute (a person approves in the app, R-HITL).
GET /g/<secret>/a2a/card returns the Agent Card JSON to paste into Gemini Enterprise (Agents -> Add agent -> A2A).
Reachable only at the secret path; there is no other way in.
"""
from __future__ import annotations

import logging
import uuid
from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .config import settings
from .services import gemini
from .services.identity import Identity

log = logging.getLogger("campus.a2a")
_HISTORY: "OrderedDict[str, list[dict]]" = OrderedDict()  # contextId -> recent turns (in memory, demo scale)
WHO = Identity("admin")  # the agent acts for timetabling staff; planning tools only create DRAFTS


def _card(base: str) -> dict:
    return {
        "protocolVersion": "0.3.0",
        "name": "Campus Time Ops",
        "description": ("AI operations agent for APU's live timetable. Ask about classes, lecturers, rooms, free rooms, holidays, "
                        "the shuttle and attendance, or report a disruption (sick lecturer, closed room, public holiday) to get a "
                        "clash-free DRAFT re-plan: substitute lecturers first, then the OR-Tools CP-SAT solver. A person approves "
                        "every plan in the Campus Time Ops app."),
        "url": base,
        "version": "1.0.0",
        "preferredTransport": "JSONRPC",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "provider": {"organization": "Team Terminal", "url": "https://campus-time-ops.onrender.com"},
        "skills": [
            {"id": "replan", "name": "Re-plan after a disruption",
             "description": "Sick or unavailable lecturer, closed room or declared holiday: drafts a clash-free plan for approval.",
             "tags": ["timetable", "replan", "substitute", "OR-Tools"],
             "examples": ["Lecturer MZD is sick tomorrow, sort out the classes", "Monday 16 Nov is now a public holiday"]},
            {"id": "lookup", "name": "Timetable questions",
             "description": "Classes, lecturers, rooms, free rooms, holidays, shuttle times, attendance risk.",
             "tags": ["timetable", "rooms", "attendance"],
             "examples": ["Which labs are free at 2pm tomorrow?", "Who else teaches Motion Graphics?"]},
        ],
    }


def _text_of(message: dict) -> str:
    out = []
    for p in message.get("parts") or []:
        if p.get("kind", p.get("type")) == "text" or "text" in p:
            out.append(str(p.get("text", "")))
    return "\n".join(x for x in out if x).strip()


def _err(rid: Any, code: int, msg: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}})


def make_router(secret: str) -> APIRouter:
    r = APIRouter(prefix=f"/g/{secret}/a2a")

    @r.get("/card")
    @r.get("/.well-known/agent-card.json")
    @r.get("/.well-known/agent.json")
    def card(request: Request):
        # behind the Next.js front the backend only sees 127.0.0.1, so advertise the public URL (RENDER_EXTERNAL_URL)
        public = settings.public_base_url.rstrip("/")
        base = f"{public}/g/{secret}/a2a" if public.startswith("https://") else str(request.url).split("/a2a")[0] + "/a2a"
        return _card(base)

    @r.post("")
    @r.post("/")
    async def rpc(request: Request):
        try:
            req = await request.json()
        except Exception:
            return _err(None, -32700, "Parse error")
        rid, method, params = req.get("id"), req.get("method"), req.get("params") or {}
        if method not in ("message/send", "tasks/send", "message/stream"):
            return _err(rid, -32601, f"Method not found: {method}")
        msg = params.get("message") or {}
        text = _text_of(msg)
        ctx = msg.get("contextId") or params.get("contextId") or params.get("sessionId") or str(uuid.uuid4())
        if not text:
            return _err(rid, -32602, "No text in message")
        hist = _HISTORY.get(ctx, [])
        import asyncio

        res = await asyncio.to_thread(gemini.answer, text, WHO, True, hist, 55.0)
        reply = res["reply"] if res else ("Sorry, I couldn't reach the planning service just now. Please try again in a moment.")
        log.info("a2a ctx=%s tools=%s ok=%s", ctx[:8], res.get("tools_used") if res else None, bool(res))
        hist = (hist + [{"role": "user", "text": text}, {"role": "model", "text": reply}])[-12:]
        _HISTORY[ctx] = hist
        _HISTORY.move_to_end(ctx)
        while len(_HISTORY) > 200:
            _HISTORY.popitem(last=False)
        out = {"kind": "message", "role": "agent", "messageId": str(uuid.uuid4()), "contextId": ctx,
               "parts": [{"kind": "text", "text": reply}]}
        if msg.get("taskId"):
            out["taskId"] = msg["taskId"]
        return {"jsonrpc": "2.0", "id": rid, "result": out}

    return r
