#!/usr/bin/env python3
"""Restore a clean demo state in < 10 s.

If the backend is running (BACKEND_URL, default http://localhost:8000) it is reset through the API so its in-memory
timetable overlay is dropped too; otherwise the local state files and outbox are wiped directly."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

t0 = time.perf_counter()
url = os.environ.get("BACKEND_URL", "http://localhost:8000")
try:
    import requests

    headers = {"Authorization": f"Bearer {os.environ['MCP_AUTH_TOKEN']}"} if os.environ.get("MCP_AUTH_TOKEN") else {}
    r = requests.post(f"{url}/api/admin/reset-demo", headers=headers, timeout=8)
    r.raise_for_status()
    print("reset via API:", r.json())
except Exception as e:
    print(f"API not reachable ({type(e).__name__}); resetting local state directly")
    from app.services.reset import reset_demo

    print(reset_demo())
print(f"done in {time.perf_counter() - t0:.2f}s")
