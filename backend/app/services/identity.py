"""Demo identity + role permissions.

The dashboard signs in as a demo persona (admin | lecturer | student); the Next.js proxy forwards it as
X-Demo-Role / X-Demo-User. Production would replace this with APU SSO (IAP / OAuth) - same permission checks.
Calls without a role header (MCP agents, scripts) are treated as 'agent' and keep the server-side R-HITL rules.

  student  : read own timetable / attendance only; cannot create disruptions or approve
  lecturer : may report THEMSELVES unavailable, find slots, and approve proposals for their own disruption
  admin    : everything (holidays, room closures, any lecturer, approvals)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .errors import Forbidden

ROLES = ("admin", "lecturer", "student")


@dataclass
class Identity:
    role: str  # admin | lecturer | student | agent
    user: Optional[str] = None  # lecturer id or student id

    @property
    def label(self) -> str:
        if self.role == "lecturer":
            return f"Lecturer {self.user}"
        if self.role == "student":
            return f"Student {self.user}"
        if self.role == "admin":
            return "Timetabling Office (demo)"
        return "agent"


def from_headers(role: Optional[str], user: Optional[str]) -> Identity:
    r = (role or "").strip().lower()
    if r not in ROLES:
        return Identity("agent", None)
    return Identity(r, (user or "").strip().upper() or None)


def can_create_disruption(who: Identity, dtype: str, scope: dict) -> None:
    if who.role in ("admin", "agent"):
        return
    if who.role == "lecturer" and dtype == "LECTURER_UNAVAILABLE" and str(scope.get("lecturer_id", "")).upper() == who.user:
        return
    if who.role == "lecturer":
        raise Forbidden("ROLE_FORBIDDEN", "Lecturers can report themselves unavailable; holidays and room closures need the timetabling office.")
    raise Forbidden("ROLE_FORBIDDEN", "Students can view their timetable and attendance but cannot change the timetable.")


def can_approve(who: Identity, proposal: dict, disruption: Optional[dict]) -> None:
    if who.role in ("admin", "agent"):
        return
    if who.role == "lecturer" and disruption and disruption.get("type") == "LECTURER_UNAVAILABLE" \
            and disruption.get("scope", {}).get("lecturer_id") == who.user:
        return
    if who.role == "lecturer" and proposal.get("kind") == "SLOT_BOOKING" and who.user in proposal.get("booking", {}).get("lecturer_ids", []):
        return
    raise Forbidden("ROLE_FORBIDDEN", f"{who.label} cannot approve this proposal; it needs the timetabling office.")
