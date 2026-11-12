"""Loads the timetable (snapshot by default, live on request with snapshot fallback), groups rows into
physical sessions, and builds the indexes everything else uses. Loaded once per process."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from ..config import settings
from ..domain import Group, Room, Session, minutes_of, parse_iso
from .catalog import build_room, group_size, school_of
from .indexes import BusyIndex
from .pseudonymise import assert_no_pii, pseudonymise_rows

log = logging.getLogger(__name__)
LIVE_URL = "https://s3-ap-southeast-1.amazonaws.com/open-ws/weektimetable"


@dataclass
class Dataset:
    meta: dict
    rows: list[dict]
    sessions: dict[str, Session]
    rooms: dict[str, Room]
    group_sizes: dict[Group, int]
    holidays: dict[date, dict]
    shuttle: dict
    intakes_listing: list[str]
    by_date: dict[date, list[str]] = field(default_factory=lambda: defaultdict(list))
    by_lecturer: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    by_group: dict[Group, list[str]] = field(default_factory=lambda: defaultdict(list))
    by_room: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    by_intake: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    room_busy: BusyIndex = field(default_factory=BusyIndex)
    group_busy: BusyIndex = field(default_factory=BusyIndex)
    lect_busy: BusyIndex = field(default_factory=BusyIndex)
    lecturer_names: dict[str, str] = field(default_factory=dict)

    @property
    def dates(self) -> list[date]:
        return sorted(self.by_date)

    def session_students(self, s: Session) -> int:
        """Headcount. Mocked group sizes can exceed the real room for combined lectures, so headcount is capped
        at the original physical room's capacity (it demonstrably fits there today). See DECISIONS.md D-07."""
        cached = self._headcount.get(s.id)
        if cached is not None:
            return cached
        total = sum(self.group_sizes.get(g, 0) for g in s.groups)
        room = self.rooms.get(s.orig_room or s.room)
        if room and room.capacity:
            fill = 0.60 + 0.35 * (int(hashlib.sha1(s.id.encode()).hexdigest()[:6], 16) / 0xFFFFFF)
            total = min(total, max(1, int(room.capacity * fill)))
        self._headcount[s.id] = total
        return total

    _headcount: dict[str, int] = field(default_factory=dict)


def _snapshot_paths(data_dir: Path) -> tuple[Path, Optional[Path]]:
    snap = data_dir / "snapshots"
    latest = (snap / "LATEST").read_text().strip()
    tt = snap / f"timetable_{latest}.json"
    it = snap / f"intakes_{latest}.json"
    return tt, (it if it.exists() else None)


def _load_rows() -> tuple[list[dict], dict, list[str]]:
    data_dir = settings.data_dir
    if settings.data_mode == "live":
        try:
            import requests

            r = requests.get(LIVE_URL, timeout=20)
            r.raise_for_status()
            rows = pseudonymise_rows(r.json())
            assert_no_pii(rows)
            log.info("DATA_MODE=live: fetched %d rows", len(rows))
            return rows, {"source": LIVE_URL, "mode": "live", "fetched_at": datetime.now().isoformat()}, []
        except Exception as e:  # any error -> snapshot
            log.warning("live fetch failed (%s); falling back to snapshot", e)
    tt, it = _snapshot_paths(data_dir)
    payload = json.loads(tt.read_text())
    meta = payload.get("meta", {}) | {"mode": "snapshot", "snapshot_file": tt.name}
    intakes = [i["INTAKE_CODE"] for i in json.loads(it.read_text())] if it else []
    return payload["rows"], meta, intakes


def _session_id(lectid: str, room: str, start_iso: str) -> str:
    return "S" + hashlib.sha1(f"{lectid}|{room}|{start_iso}".encode()).hexdigest()[:10]


def build_dataset(rows: list[dict], meta: dict, intakes: list[str]) -> Dataset:
    data_dir = settings.data_dir
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in rows:
        grouped[(r["LECTID"], r["ROOM"], r["TIME_FROM_ISO"])].append(r)

    sessions: dict[str, Session] = {}
    for (lect, room, start_iso), rs in grouped.items():
        st = parse_iso(start_iso)
        en = parse_iso(rs[0]["TIME_TO_ISO"])
        groups = sorted({(r["INTAKE"], r["GROUPING"]) for r in rs})
        sid = _session_id(lect, room, start_iso)
        sessions[sid] = Session(
            id=sid,
            date=st.date(),
            start_min=minutes_of(st),
            end_min=minutes_of(en),
            module_name=rs[0]["MODULE_NAME"],
            module_ids=sorted({r["MODID"] for r in rs}),
            class_codes=sorted({r["CLASS_CODE"] for r in rs}),
            lecturer_id=lect,
            lecturer_name=rs[0]["NAME"],
            room=room,
            location=rs[0]["LOCATION"],
            school=school_of(rs[0]["CLASS_CODE"]),
            groups=groups,
        )

    # rooms: committed mock file if present, else deterministic in-memory build
    rooms: dict[str, Room] = {}
    rooms_file = data_dir / "rooms.json"
    if rooms_file.exists():
        for r in json.loads(rooms_file.read_text()):
            rooms[r["name"]] = Room(**r)
    for s in sessions.values():
        if s.room not in rooms:
            rooms[s.room] = build_room(s.room)
    if "ONLINE" not in rooms:
        rooms["ONLINE"] = build_room("ONLINE")

    gs_file = data_dir / "group_sizes.json"
    gsizes: dict[Group, int] = {}
    if gs_file.exists():
        for k, v in json.loads(gs_file.read_text()).items():
            i, g = k.split("|")
            gsizes[(i, g)] = v
    for s in sessions.values():
        for g in s.groups:
            gsizes.setdefault(g, group_size(*g))

    hol_raw = json.loads((data_dir / "holidays_2026.json").read_text())
    holidays: dict[date, dict] = {}
    for h in hol_raw["holidays"]:
        d = date.fromisoformat(h["date"])
        if d in holidays:
            holidays[d]["name"] += " / " + h["name"]
        else:
            holidays[d] = dict(h)
    shuttle = json.loads((data_dir / "shuttle.json").read_text())

    ds = Dataset(
        meta=meta,
        rows=rows,
        sessions=sessions,
        rooms=rooms,
        group_sizes=gsizes,
        holidays=holidays,
        shuttle=shuttle,
        intakes_listing=intakes,
    )
    for sid, s in sorted(sessions.items(), key=lambda kv: (kv[1].date, kv[1].start_min, kv[0])):
        ds.by_date[s.date].append(sid)
        ds.by_lecturer[s.lecturer_id].append(sid)
        ds.by_room[s.room].append(sid)
        ds.room_busy.add(s.room, s.date, s.start_min, s.end_min, sid)
        ds.lect_busy.add(s.lecturer_id, s.date, s.start_min, s.end_min, sid)
        ds.lecturer_names[s.lecturer_id] = s.lecturer_name
        for g in s.groups:
            ds.by_group[g].append(sid)
            ds.by_intake[g[0]].add(g[1])
            ds.group_busy.add(g, s.date, s.start_min, s.end_min, sid)
    return ds


_lock = threading.Lock()
_ds: Optional[Dataset] = None


def get_dataset() -> Dataset:
    global _ds
    if _ds is None:
        with _lock:
            if _ds is None:
                rows, meta, intakes = _load_rows()
                _ds = build_dataset(rows, meta, intakes)
                log.info("dataset loaded: %d rows, %d physical sessions", len(rows), len(_ds.sessions))
    return _ds


def reset_dataset() -> None:
    global _ds
    with _lock:
        _ds = None
