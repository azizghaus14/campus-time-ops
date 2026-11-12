"""Core domain model. Plain dataclasses internally (fast for 25k rows); dicts at the API/MCP boundary."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

Group = tuple[str, str]  # (INTAKE, GROUPING) - the real clash unit: an intake group shares one timetable


class DisruptionType(str, Enum):
    LECTURER_UNAVAILABLE = "LECTURER_UNAVAILABLE"
    ROOM_UNAVAILABLE = "ROOM_UNAVAILABLE"
    HOLIDAY = "HOLIDAY"


class ProposalStatus(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    SUPERSEDED = "SUPERSEDED"


class ProposalKind(str, Enum):
    REPLAN = "REPLAN"
    SLOT_BOOKING = "SLOT_BOOKING"
    ESCALATION = "ESCALATION"


@dataclass
class Room:
    name: str
    type: str  # classroom | auditorium | lab | specialist_lab | discussion | culinary | presentation | online
    capacity: int  # 0 == unlimited (online)
    block: str
    floor: Optional[int] = None
    online: bool = False
    air_conditioned: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Session:
    """One PHYSICAL session: same lecturer + room + start time, possibly many intakes (combined lecture)."""

    id: str
    date: date
    start_min: int  # minutes since midnight MYT
    end_min: int
    module_name: str
    module_ids: list[str]
    class_codes: list[str]
    lecturer_id: str
    lecturer_name: str
    room: str
    location: str
    school: str
    groups: list[Group] = field(default_factory=list)
    # set when an executed proposal moved this session (overlay on top of the feed)
    orig_room: Optional[str] = None
    orig_date: Optional[date] = None
    orig_start_min: Optional[int] = None
    moved_by: Optional[str] = None

    @property
    def duration(self) -> int:
        return self.end_min - self.start_min

    @property
    def day(self) -> str:
        return self.date.strftime("%a").upper()

    def start_iso(self) -> str:
        return iso(self.date, self.start_min)

    def end_iso(self) -> str:
        return iso(self.date, self.end_min)

    def to_dict(self, group_sizes: Optional[dict] = None) -> dict:
        d = {
            "id": self.id,
            "date": self.date.isoformat(),
            "day": self.day,
            "start": self.start_iso(),
            "end": self.end_iso(),
            "time": f"{hhmm(self.start_min)}-{hhmm(self.end_min)}",
            "duration_min": self.duration,
            "module_name": self.module_name,
            "module_ids": self.module_ids,
            "class_codes": self.class_codes,
            "lecturer_id": self.lecturer_id,
            "lecturer_name": self.lecturer_name,
            "room": self.room,
            "location": self.location,
            "school": self.school,
            "groups": [{"intake": i, "grouping": g} for i, g in self.groups],
            "n_groups": len(self.groups),
        }
        if self.moved_by:
            d["moved_by"] = self.moved_by
            d["original"] = {
                "date": self.orig_date.isoformat() if self.orig_date else None,
                "start_min": self.orig_start_min,
                "room": self.orig_room,
            }
        if group_sizes is not None:
            d["students"] = sum(group_sizes.get(g, 0) for g in self.groups)
        return d


@dataclass
class Disruption:
    id: str
    type: DisruptionType
    scope: dict[str, Any]  # {"lecturer_id": ...} | {"rooms": [...]} | {"date": ...}
    window: dict[str, str]  # {"start": iso, "end": iso}
    reason: str
    created_by: str
    created_at: str
    affected_session_ids: list[str] = field(default_factory=list)
    impact: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        return d


@dataclass
class Move:
    session_id: str
    from_: dict  # {start, end, room}
    to: dict  # {start, end, room, online}
    affected_groups: list[dict]
    rationale: str
    rule_ids: list[str]
    module_name: str = ""
    lecturer_id: str = ""
    school: str = ""
    students: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["from"] = d.pop("from_")
        return d


@dataclass
class AuditEvent:
    id: str
    who: str
    what: str
    when: str
    proposal_id: Optional[str] = None
    before: Any = None
    after: Any = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Student:
    id: str
    name: str
    intake: str
    grouping: str
    nationality: str
    is_international: bool
    pass_expiry: Optional[str]
    passport_no: Optional[str]
    passport_expiry: Optional[str]
    dob: Optional[str]
    sex: Optional[str]
    advisor_id: Optional[str]
    profile: str
    attendance_records: list[dict] = field(default_factory=list)

    def to_dict(self, with_records: bool = False) -> dict:
        d = asdict(self)
        if not with_records:
            d.pop("attendance_records")
        return d


def hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def iso(d: date, minutes: int) -> str:
    return f"{d.isoformat()}T{hhmm(minutes)}:00+08:00"


def parse_iso(s: str) -> datetime:
    from .config import MYT

    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MYT)
    return dt.astimezone(MYT)


def minutes_of(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute
