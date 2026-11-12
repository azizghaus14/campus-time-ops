"""Central configuration. Everything is overridable via environment variables (.env supported)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except Exception:  # pragma: no cover
    pass

MYT = timezone(timedelta(hours=8), name="MYT")
REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[2]))


def _b(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    gcp_project: str = os.environ.get("GCP_PROJECT", "")
    region: str = os.environ.get("REGION", "asia-southeast1")
    data_mode: str = os.environ.get("DATA_MODE", "snapshot")
    demo_now: str = os.environ.get("DEMO_NOW", "2026-11-12T09:00:00+08:00")
    term_end: str = os.environ.get("TERM_END", "2026-12-18")

    attendance_threshold: float = float(os.environ.get("ATTENDANCE_THRESHOLD", "0.80"))
    notice_hours: int = int(os.environ.get("NOTICE_HOURS", "24"))
    shuttle_buffer_min: int = int(os.environ.get("SHUTTLE_BUFFER_MIN", "15"))
    shuttle_include_limited: bool = _b("SHUTTLE_INCLUDE_LIMITED", False)

    store_backend: str = os.environ.get("STORE_BACKEND", "json")
    workspace_mode: str = os.environ.get("WORKSPACE_MODE", "local")
    workspace_demo_domain: str = os.environ.get("WORKSPACE_DEMO_DOMAIN", "demo.example.edu")
    oauth_token_file: str = os.environ.get("GOOGLE_OAUTH_TOKEN_FILE", "")
    changelog_doc_id: str = os.environ.get("CHANGELOG_DOC_ID", "")

    gemini_model: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")
    mcp_auth_token: str = os.environ.get("MCP_AUTH_TOKEN", "")
    rate_limit_per_min: int = int(os.environ.get("RATE_LIMIT_PER_MIN", "120"))
    public_base_url: str = os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8000")
    dashboard_base_url: str = os.environ.get("DASHBOARD_BASE_URL", "http://localhost:3000")

    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("DATA_DIR", REPO_ROOT / "data")))
    grounding_dir: Path = field(default_factory=lambda: REPO_ROOT / "grounding")

    @property
    def state_dir(self) -> Path:
        return Path(os.environ.get("STATE_DIR", self.data_dir / "state"))

    @property
    def outbox_dir(self) -> Path:
        return Path(os.environ.get("OUTBOX_DIR", self.data_dir / "outbox"))

    def now(self) -> datetime:
        """The system clock. A fixed DEMO_NOW makes the snapshot demo reproducible."""
        if self.demo_now:
            return datetime.fromisoformat(self.demo_now).astimezone(MYT)
        return datetime.now(MYT)


settings = Settings()

# Standard APU 2-hour slot grid (dominates the feed). Times are minutes since midnight.
STANDARD_STARTS = [8 * 60 + 30, 10 * 60 + 45, 13 * 60 + 30, 15 * 60 + 45, 18 * 60 + 45]
DAY_START_MIN = 8 * 60 + 30
DAY_END_MIN = 21 * 60
TICK_MIN = 15
EVENING_START_MIN = 18 * 60
