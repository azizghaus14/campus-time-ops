"""Campus Time Ops backend: FastAPI REST (/api) + MCP streamable HTTP (/mcp) in one process."""
from __future__ import annotations

import contextlib
import logging
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import settings
from .data.loader import get_dataset
from .mcp_server import mcp
from .services.errors import ToolError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("campus-time-ops")


def warm_start() -> dict:
    from .services.replan import replay_executed
    from .services.slots import replay_bookings

    ds = get_dataset()
    n = replay_executed()
    b = replay_bookings()
    log.info("ready: %d sessions (%s), replayed %d executed proposals, %d bookings", len(ds.sessions), ds.meta.get("mode"), n, b)
    return {"replayed": n, "bookings": b}


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    warm_start()
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Campus Time Ops", version="0.1.0", lifespan=lifespan,
              description="AI operations layer on APU's live timetable. REST for the dashboard; the same tools over MCP at /mcp.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_hits: dict[str, deque] = defaultdict(deque)
_OPEN_PATHS = ("/api/health", "/docs", "/openapi.json", "/outbox", "/demo-passports")


@app.middleware("http")
async def auth_and_rate_limit(request: Request, call_next):
    path = request.url.path
    # rate limit (per client, sliding 60s window)
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    now = time.monotonic()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= settings.rate_limit_per_min and not path.startswith("/outbox"):
        return JSONResponse({"error": {"code": "RATE_LIMITED", "message": "too many requests"}}, status_code=429)
    q.append(now)
    # bearer token: always required for /mcp when configured; for /api mutations when REQUIRE_API_AUTH
    token = settings.mcp_auth_token
    needs = token and (path.startswith("/mcp") or (path.startswith("/api") and request.method != "GET" and _api_auth_required()))
    if needs and not path.startswith(_OPEN_PATHS):
        if request.headers.get("authorization", "") != f"Bearer {token}":
            return JSONResponse({"error": {"code": "UNAUTHORIZED", "message": "missing or invalid bearer token"}}, status_code=401)
    return await call_next(request)


def _api_auth_required() -> bool:
    import os

    return os.environ.get("REQUIRE_API_AUTH", "false").lower() in ("1", "true", "yes")


@app.exception_handler(ToolError)
async def tool_error(_: Request, e: ToolError):
    return JSONResponse(e.to_dict(), status_code=e.status)


@app.exception_handler(Exception)
async def unhandled(_: Request, e: Exception):
    log.exception("unhandled error")
    return JSONResponse({"error": {"code": "INTERNAL", "message": str(e)[:300]}}, status_code=500)


app.include_router(router)


@app.post("/api/admin/reset-demo")
def reset_demo():
    from .services.reset import reset_demo as _reset

    return _reset()


settings.outbox_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outbox", StaticFiles(directory=str(settings.outbox_dir)), name="outbox")
if (settings.data_dir / "demo_passports").exists():
    app.mount("/demo-passports", StaticFiles(directory=str(settings.data_dir / "demo_passports")), name="passports")
# MCP streamable HTTP at /mcp (mounted last so /api routes match first)
app.mount("/", mcp.streamable_http_app())
