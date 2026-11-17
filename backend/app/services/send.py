"""Send one reviewed email draft, only when a person presses Send (R-HITL: the system never sends on its own).

Delivery: if SMTP_HOST / SMTP_USER / SMTP_PASSWORD are set (e.g. a Gmail app password), the draft is really sent.
Otherwise it is recorded as sent in DEMO mode and nothing is delivered; the UI says so.
Every send is written to the audit log with who pressed Send.
"""
from __future__ import annotations

import email
import os
import re
import smtplib
from email import policy

from ..config import settings
from .audit import log_event
from .errors import Conflict, NotFound
from .identity import Identity
from .store import get_store

_FILE = re.compile(r"^draft_\d{3}\.eml$")
_PID = re.compile(r"^PRO-\d{4}$")


def _smtp() -> dict | None:
    host, user, pw = (os.environ.get(k, "").strip() for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))
    if not (host and user and pw):
        return None
    return {"host": host, "port": int(os.environ.get("SMTP_PORT", "587")), "user": user, "pw": pw,
            "from": os.environ.get("SMTP_FROM", user)}


def mode() -> str:
    return "smtp" if _smtp() else "demo"


def list_sent(pid: str) -> dict:
    sent = [d for d in get_store().list("sent") if d.get("proposal_id") == pid]
    return {"mode": mode(), "sent": {d["file"]: d for d in sent}}


def send_draft(pid: str, file: str, who: Identity) -> dict:
    if not _PID.match(pid) or not _FILE.match(file):
        raise NotFound("UNKNOWN_DRAFT", "No such draft.")
    path = settings.outbox_dir / pid / "drafts" / file
    if not path.exists():
        raise NotFound("UNKNOWN_DRAFT", "No such draft (was the demo reset?).")
    st = get_store()
    key = f"{pid}:{file}"
    if st.get("sent", key):
        raise Conflict("ALREADY_SENT", "This draft was already sent.")
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    del msg["X-Campus-Time-Ops"]
    cfg = _smtp()
    if cfg:
        if msg["From"]:
            msg.replace_header("From", cfg["from"])
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as s:
            s.starttls()
            s.login(cfg["user"], cfg["pw"])
            s.send_message(msg)
    rec = {"id": key, "proposal_id": pid, "file": file, "to": str(msg["To"] or ""), "subject": str(msg["Subject"] or ""),
           "mode": "smtp" if cfg else "demo", "sent_by": who.label, "sent_at": settings.now().isoformat(timespec="seconds")}
    st.put("sent", key, rec)
    log_event(who.label, "email_sent" if cfg else "email_sent_demo", pid, after={k: rec[k] for k in ("to", "subject", "mode")})
    return rec
