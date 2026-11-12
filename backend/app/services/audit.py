"""Append-only audit log: every proposal, approval, rejection and action."""
from __future__ import annotations

from typing import Any, Optional

from ..config import settings
from ..domain import AuditEvent
from .store import get_store


def log_event(who: str, what: str, proposal_id: Optional[str] = None, before: Any = None, after: Any = None) -> dict:
    st = get_store()
    ev = AuditEvent(
        id=st.next_id("AUD"),
        who=who or "system",
        what=what,
        when=settings.now().isoformat(timespec="seconds") if settings.demo_now else _wall(),
        proposal_id=proposal_id,
        before=before,
        after=after,
    )
    d = ev.to_dict()
    d["wall_clock"] = _wall()
    st.put("audit", ev.id, d)
    return d


def _wall() -> str:
    from datetime import datetime

    from ..config import MYT

    return datetime.now(MYT).isoformat(timespec="seconds")


def list_audit(proposal_id: Optional[str] = None, limit: int = 500) -> list[dict]:
    st = get_store()
    evs = st.list("audit", proposal_id=proposal_id) if proposal_id else st.list("audit")
    evs.sort(key=lambda e: e["id"], reverse=True)
    return evs[:limit]
