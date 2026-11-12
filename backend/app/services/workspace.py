"""Workspace actions: Calendar events, Gmail DRAFTS (never sent by the system), change-log Doc.

Two providers behind one interface:
  LocalWorkspace  (WORKSPACE_MODE=local, default): writes real .ics / .eml / .md artefacts into data/outbox and returns
                  links served by the API at /outbox/... - fully offline, used for the recorded demo fallback.
  GoogleWorkspace (WORKSPACE_MODE=google): Google Calendar API, Gmail API (drafts.create only), Docs API.
                  DEMO WORKSPACE ACCOUNTS ONLY - every recipient must be on WORKSPACE_DEMO_DOMAIN.

These functions are only ever called from proposals.execute_* which enforces an APPROVED proposal (R-HITL).
"""
from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, Protocol

from ..config import MYT, settings
from ..domain import parse_iso
from .errors import Forbidden


@dataclass
class CalendarEvent:
    summary: str
    start: str  # ISO
    end: str
    location: str
    description: str
    attendees: list[str]
    uid: str


@dataclass
class Draft:
    to: list[str]
    bcc: list[str]
    subject: str
    body: str


def _inbox() -> Optional[tuple[str, str]]:
    """WORKSPACE_DEMO_INBOX=you@gmail.com -> every demo recipient becomes a '+' alias of that one inbox
    (you+lect-mzd@gmail.com), so a personal Google account works and nothing can reach a real person."""
    box = os.environ.get("WORKSPACE_DEMO_INBOX", "").strip().lower()
    if "@" in box:
        local, dom = box.split("@", 1)
        return local, dom
    return None


def _addr(tag: str, sub: str = "") -> str:
    tag = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9._-]+", "-", tag.lower())).strip("-")
    ib = _inbox()
    if ib:
        return f"{ib[0]}+{tag}@{ib[1]}"
    return f"{tag}@{sub}{settings.workspace_demo_domain}"


def addr_lecturer(lid: str) -> str:
    return _addr(f"lect-{lid}")


def addr_intake(intake: str, grouping: Optional[str] = None) -> str:
    g = f"-{grouping}" if grouping else ""
    return _addr(f"{intake}{g}", "students.")


def addr_role(role: str) -> str:
    return _addr(role)


def _guard(addrs: list[str]) -> None:
    ib = _inbox()
    dom = settings.workspace_demo_domain.lower()
    for a in addrs:
        a = a.lower()
        if ib:
            ok = a.endswith("@" + ib[1]) and (a.split("@")[0] == ib[0] or a.split("@")[0].startswith(ib[0] + "+"))
        else:
            ok = a.endswith("@" + dom) or a.endswith("." + dom)
        if not ok:
            raise Forbidden("NON_DEMO_RECIPIENT", f"Refusing recipient outside the demo inbox/domain: {a}")


class Workspace(Protocol):
    mode: str

    def create_events(self, ref: str, events: list[CalendarEvent]) -> dict: ...
    def create_drafts(self, ref: str, drafts: list[Draft]) -> dict: ...
    def append_changelog(self, ref: str, title: str, markdown: str) -> dict: ...


def _ics_dt(s: str) -> str:
    return parse_iso(s).astimezone().strftime("%Y%m%dT%H%M%S")


def _ics(events: list[CalendarEvent]) -> str:
    stamp = datetime.now(MYT).strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Campus Time Ops//Demo//EN", "CALSCALE:GREGORIAN",
           "BEGIN:VTIMEZONE", "TZID:Asia/Kuala_Lumpur", "BEGIN:STANDARD", "DTSTART:19700101T000000",
           "TZOFFSETFROM:+0800", "TZOFFSETTO:+0800", "END:STANDARD", "END:VTIMEZONE"]
    for e in events:
        desc = e.description.replace("\n", "\\n").replace(",", "\\,")
        out += [
            "BEGIN:VEVENT", f"UID:{e.uid}", f"DTSTAMP:{stamp}",
            f"DTSTART;TZID=Asia/Kuala_Lumpur:{parse_iso(e.start).strftime('%Y%m%dT%H%M%S')}",
            f"DTEND;TZID=Asia/Kuala_Lumpur:{parse_iso(e.end).strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{e.summary}", f"LOCATION:{e.location}", f"DESCRIPTION:{desc}",
        ]
        out += [f"ATTENDEE;RSVP=FALSE:mailto:{a}" for a in e.attendees[:50]]
        out.append("END:VEVENT")
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"


class LocalWorkspace:
    mode = "local"

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or settings.outbox_dir
        self.root.mkdir(parents=True, exist_ok=True)

    def _url(self, p: Path) -> str:
        return f"{settings.public_base_url}/outbox/{p.relative_to(self.root).as_posix()}"

    def create_events(self, ref: str, events: list[CalendarEvent]) -> dict:
        for e in events:
            _guard(e.attendees)
        d = self.root / ref / "calendar"
        d.mkdir(parents=True, exist_ok=True)
        links = []
        for e in events:
            p = d / f"{re.sub(r'[^A-Za-z0-9_-]', '_', e.uid)}.ics"
            p.write_text(_ics([e]))
            links.append({"summary": e.summary, "start": e.start, "url": self._url(p)})
        allp = self.root / ref / "calendar_all.ics"
        allp.write_text(_ics(events))
        return {"count": len(events), "bundle_url": self._url(allp), "events": links}

    def create_drafts(self, ref: str, drafts: list[Draft]) -> dict:
        d = self.root / ref / "drafts"
        d.mkdir(parents=True, exist_ok=True)
        out = []
        for i, dr in enumerate(drafts, 1):
            _guard(dr.to + dr.bcc)
            msg = EmailMessage()
            msg["From"] = addr_role("timetabling")
            msg["To"] = ", ".join(dr.to)
            if dr.bcc:
                msg["Bcc"] = ", ".join(dr.bcc)
            msg["Subject"] = dr.subject
            msg["X-Campus-Time-Ops"] = f"DRAFT - not sent ({ref})"
            msg.set_content(dr.body)
            p = d / f"draft_{i:03d}.eml"
            p.write_bytes(bytes(msg))
            out.append({"id": f"{ref}-d{i:03d}", "to": dr.to, "bcc_count": len(dr.bcc), "subject": dr.subject, "url": self._url(p), "status": "DRAFT"})
        index = self.root / ref / "drafts_index.json"
        index.write_text(json.dumps(out, indent=1))
        return {"count": len(out), "index_url": self._url(index), "drafts": out}

    def append_changelog(self, ref: str, title: str, markdown: str) -> dict:
        p = self.root / "Timetable_Change_Log.md"
        if not p.exists():
            p.write_text("# Timetable Change Log (Campus Time Ops - demo)\n\nEvery entry below was approved by a human before it was written.\n\n")
        with p.open("a") as f:
            f.write(f"\n---\n\n## {title}\n\n{markdown}\n")
        return {"doc_url": self._url(p), "title": "Timetable Change Log"}


class GoogleWorkspace:  # pragma: no cover - needs demo Workspace credentials
    mode = "google"

    def __init__(self) -> None:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        scopes = [
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/gmail.compose",
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/drive.file",
        ]
        creds = Credentials.from_authorized_user_file(settings.oauth_token_file, scopes)
        self.cal = build("calendar", "v3", credentials=creds, cache_discovery=False)
        self.gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
        self.docs = build("docs", "v1", credentials=creds, cache_discovery=False)
        self.calendar_id = "primary"

    def create_events(self, ref: str, events: list[CalendarEvent]) -> dict:
        out = []
        for e in events:
            _guard(e.attendees)
            body = {
                "summary": e.summary, "location": e.location, "description": e.description,
                "start": {"dateTime": e.start, "timeZone": "Asia/Kuala_Lumpur"},
                "end": {"dateTime": e.end, "timeZone": "Asia/Kuala_Lumpur"},
                "attendees": [{"email": a} for a in e.attendees[:50]],
                "extendedProperties": {"private": {"campus_time_ops_ref": ref}},
            }
            ev = self.cal.events().insert(calendarId=self.calendar_id, body=body, sendUpdates="none").execute()
            out.append({"summary": e.summary, "start": e.start, "url": ev.get("htmlLink"), "id": ev.get("id")})
        return {"count": len(out), "events": out}

    def create_drafts(self, ref: str, drafts: list[Draft]) -> dict:
        import base64

        out = []
        for dr in drafts:
            _guard(dr.to + dr.bcc)
            msg = EmailMessage()
            msg["To"] = ", ".join(dr.to)
            if dr.bcc:
                msg["Bcc"] = ", ".join(dr.bcc)
            msg["Subject"] = dr.subject
            msg.set_content(dr.body)
            raw = base64.urlsafe_b64encode(bytes(msg)).decode()
            d = self.gmail.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
            out.append({"id": d["id"], "to": dr.to, "subject": dr.subject, "url": f"https://mail.google.com/mail/u/0/#drafts?compose={d['message']['id']}", "status": "DRAFT"})
        return {"count": len(out), "drafts": out}

    def _append(self, doc_id: str, text: str) -> None:
        doc = self.docs.documents().get(documentId=doc_id).execute()
        end = doc["body"]["content"][-1]["endIndex"] - 1
        self.docs.documents().batchUpdate(documentId=doc_id, body={"requests": [{"insertText": {"location": {"index": end}, "text": text}}]}).execute()

    def append_changelog(self, ref: str, title: str, markdown: str) -> dict:
        doc_id = settings.changelog_doc_id
        if not doc_id:
            doc_id = self.docs.documents().create(body={"title": "Timetable Change Log (Campus Time Ops demo)"}).execute()["documentId"]
            settings.changelog_doc_id = doc_id
        self._append(doc_id, f"\n{title}\n{markdown}\n")
        return {"doc_url": f"https://docs.google.com/document/d/{doc_id}/edit", "title": "Timetable Change Log", "doc_id": doc_id}




_ws: Optional[Workspace] = None


def get_workspace() -> Workspace:
    global _ws
    if _ws is None:
        _ws = GoogleWorkspace() if settings.workspace_mode == "google" else LocalWorkspace()
    return _ws


def set_workspace(ws: Optional[Workspace]) -> None:
    global _ws
    _ws = ws


def new_uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@campus-time-ops"
