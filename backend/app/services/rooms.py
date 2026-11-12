"""Room tools: schedule, free-room search, utilisation heatmap (room x hour, per block), empty rooms right now."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Optional

from ..config import DAY_END_MIN, DAY_START_MIN, settings
from ..data.loader import get_dataset
from ..domain import hhmm, parse_iso
from .errors import NotFound, require
from .timetable import date_range, parse_date, sdict

def get_room_schedule(room: str, date_str: str) -> dict:
    ds = get_dataset()
    if room not in ds.rooms:
        import difflib

        raise NotFound("UNKNOWN_ROOM", f"No room '{room}'", suggestions=difflib.get_close_matches(room, list(ds.rooms), n=5))
    d = parse_date(date_str)
    ss = [ds.sessions[i] for i in ds.by_room.get(room, []) if ds.sessions[i].date == d]
    ss.sort(key=lambda s: s.start_min)
    return {"room": ds.rooms[room].to_dict(), "date": d.isoformat(), "sessions": [sdict(ds, s) for s in ss]}


def find_free_rooms(start: str, end: str, min_capacity: int = 0, room_type: Optional[str] = None, limit: int = 50) -> dict:
    ds = get_dataset()
    a, b = parse_iso(start), parse_iso(end)
    require(a.date() == b.date() and a < b, "BAD_WINDOW", "start/end must be on the same day and start < end")
    d, s_min, e_min = a.date(), a.hour * 60 + a.minute, b.hour * 60 + b.minute
    out = []
    for r in ds.rooms.values():
        if r.online:
            continue
        if room_type and r.type != room_type:
            continue
        if r.capacity < int(min_capacity or 0):
            continue
        if ds.room_busy.is_free(r.name, d, s_min, e_min):
            out.append(r.to_dict())
    out.sort(key=lambda r: (r["capacity"], r["name"]))
    return {"window": {"start": start, "end": end}, "count": len(out), "rooms": out[:limit]}


def get_room_utilisation(start_date: str, end_date: str, room_type: Optional[str] = None, include_online: bool = False) -> dict:
    """Utilisation per room per hour (08:00-21:00) averaged over the working days in range."""
    ds = get_dataset()
    a, b = date_range(start_date, end_date)
    days = [a + timedelta(days=i) for i in range((b - a).days + 1)]
    days = [d for d in days if d.weekday() < 5 and ds.by_date.get(d)]
    hours = list(range(8, 21))
    rows = []
    for r in sorted(ds.rooms.values(), key=lambda r: (r.type, r.name)):
        if r.name == "ONLINE" or (r.online and not include_online) or (room_type and r.type != room_type):
            continue
        cells = []
        for h in hours:
            busy = 0
            for d in days:
                for s, e, _ in ds.room_busy.intervals(r.name, d):
                    busy += max(0, min(e, (h + 1) * 60) - max(s, h * 60))
            cells.append(round(busy / (60 * max(1, len(days))), 3))
        rows.append({"room": r.name, "type": r.type, "block": r.block, "capacity": r.capacity, "hours": cells,
                     "avg": round(sum(cells) / len(cells), 3)})
    by_hour = [round(sum(r["hours"][i] for r in rows) / max(1, len(rows)), 3) for i in range(len(hours))]
    blocks: dict[str, list] = defaultdict(list)
    for r in rows:
        blocks[r["block"]].append(r["avg"])
    by_block = sorted(({"block": b, "rooms": len(v), "utilisation": round(sum(v) / len(v), 3)} for b, v in blocks.items()),
                      key=lambda x: -x["utilisation"])
    return {
        "range": {"start": a.isoformat(), "end": b.isoformat(), "working_days": len(days)},
        "hours": [f"{h:02d}:00" for h in hours],
        "rooms": rows,
        "campus_by_hour": by_hour,
        "campus_avg": round(sum(by_hour) / len(by_hour), 3),
        "by_block": by_block,
    }


def empty_rooms_now(at: Optional[str] = None) -> dict:
    """Physical rooms with no class at a moment (default: now), and how long they stay free."""
    ds = get_dataset()
    now = parse_iso(at) if at else settings.now()
    d, m = now.date(), now.hour * 60 + now.minute
    empty, busy = [], 0
    for r in ds.rooms.values():
        if r.online:
            continue
        ivs = ds.room_busy.intervals(r.name, d)
        if any(s <= m < e for s, e, _ in ivs):
            busy += 1
            continue
        nxt = min((s for s, e, _ in ivs if s > m), default=None)
        free_until = nxt if nxt is not None else DAY_END_MIN
        empty.append({"room": r.name, "type": r.type, "block": r.block, "capacity": r.capacity,
                      "free_until": hhmm(free_until), "free_hours": round(max(0, free_until - max(m, DAY_START_MIN)) / 60, 2)})
    empty.sort(key=lambda x: (-x["free_hours"], x["room"]))
    return {"at": now.isoformat(), "empty_count": len(empty), "in_use_count": busy,
            "share_empty": round(len(empty) / max(1, len(empty) + busy), 3), "rooms": empty}
