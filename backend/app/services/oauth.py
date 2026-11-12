"""Google OAuth access tokens on /mcp.

Gemini Enterprise's "Custom MCP Server" connector authenticates with OAuth 2.0 (Google's authorization + token
URLs and a Web-application OAuth client you create). Besides the static MCP_AUTH_TOKEN, the MCP endpoint therefore
accepts a Google access token when:
  - it was issued to one of MCP_GOOGLE_CLIENT_IDS (comma-separated OAuth client IDs), and
  - if MCP_ALLOWED_EMAILS is set, the signed-in user's email is on that list.
Tokens are verified with Google's tokeninfo endpoint and cached until they expire.
"""
from __future__ import annotations

import os
import time
from typing import Optional

import requests

_cache: dict[str, float] = {}


def _csv(name: str) -> set[str]:
    return {x.strip().lower() for x in os.environ.get(name, "").split(",") if x.strip()}


def enabled() -> bool:
    return bool(_csv("MCP_GOOGLE_CLIENT_IDS"))


def verify(token: str, fetch=None) -> Optional[str]:
    """-> the user's email (or 'ok') if valid, else None."""
    if not token or not enabled():
        return None
    exp = _cache.get(token)
    if exp and exp > time.time():
        return "cached"
    try:
        info = (fetch or _tokeninfo)(token)
    except Exception:
        return None
    clients = _csv("MCP_GOOGLE_CLIENT_IDS")
    if str(info.get("aud", "")).lower() not in clients and str(info.get("azp", "")).lower() not in clients:
        return None
    allowed = _csv("MCP_ALLOWED_EMAILS")
    email = str(info.get("email", "")).lower()
    if allowed and email not in allowed:
        return None
    _cache[token] = time.time() + min(3600, int(info.get("expires_in", 300)))
    return email or "ok"


def _tokeninfo(token: str) -> dict:
    r = requests.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": token}, timeout=5)
    r.raise_for_status()
    return r.json()
