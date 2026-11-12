"""Room tools: schedule, free-room search, utilisation heatmap, empty-rooms-now + energy estimate."""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import timedelta
from typing import Optional

from ..config import DAY_END_MIN, DAY_START_MIN, settings
from ..data.loader import get_dataset
from ..domain import hhmm, parse_iso
from .errors import NotFound, require
from .timetable import date_range, parse_date, sdict

# Clearly-labelled ASSUMPTIONS for the energy estimate (override via env).
KWH_PER_EMPTY_AC_ROOM_HOUR = float(os.environ.get("KWH_PER_EMPTY_AC_ROOM_HOUR", "3.5"))
RM_PER_KWH = float(os.environ.get("RM_PER_KWH", "0.509"))


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
    return {
        "range": {"start": a.isoformat(), "end": b.isoformat(), "working_days": len(days)},
        "hours": [f"{h:02d}:00" for h in hours],
        "rooms": rows,
        "campus_by_hour": by_hour,
        "campus_avg": round(sum(by_hour) / len(by_hour), 3),
    }


def empty_rooms_now(at: Optional[str] = None) -> dict:
    """Rooms with no class right now, plus an energy-saving estimate if their A/C is off until the next class."""
    ds = get_dataset()
    now = parse_iso(at) if at else settings.now()
    d, m = now.date(), now.hour * 60 + now.minute
    empty = []
    for r in ds.rooms.values():
        if r.online:
            continue
        ivs = ds.room_busy.intervals(r.name, d)
        if any(s <= m < e for s, e, _ in ivs):
            continue
        nxt = min((s for s, e, _ in ivs if s > m), default=None)
        free_until = nxt if nxt is not None else DAY_END_MIN
        empty.append({"room": r.name, "type": r.type, "capacity": r.capacity,
                      "free_until": hhmm(free_until), "free_hours": round((free_until - max(m, DAY_START_MIN)) / 60, 2)})
    empty.sort(key=lambda x: (-x["free_hours"], x["room"]))
    room_hours = sum(max(0, x["free_hours"]) for x in empty if x["type"] != "online")
    # whole-day idle room-hours across the operating day (08:30-21:00)
    day_idle = 0.0
    for r in ds.rooms.values():
        if r.online:
            continue
        busy = ds.room_busy.busy_minutes(r.name, d)
        day_idle += max(0, (DAY_END_MIN - DAY_START_MIN) - busy) / 60
    kwh_now = room_hours * KWH_PER_EMPTY_AC_ROOM_HOUR
    kwh_day = day_idle * KWH_PER_EMPTY_AC_ROOM_HOUR
    return {
        "at": now.isoformat(),
        "empty_count": len(empty),
        "rooms": empty,
        "energy": {
            "assumptions": {
                "kwh_per_empty_ac_room_hour": KWH_PER_EMPTY_AC_ROOM_HOUR,
                "rm_per_kwh": RM_PER_KWH,
                "label": "ASSUMPTION - illustrative only; tune KWH_PER_EMPTY_AC_ROOM_HOUR / RM_PER_KWH",
            },
            "remaining_idle_room_hours_today": round(room_hours, 1),
            "potential_kwh_rest_of_today": round(kwh_now, 0),
            "potential_rm_rest_of_today": round(kwh_now * RM_PER_KWH, 0),
            "idle_room_hours_full_day": round(day_idle, 1),
            "potential_kwh_full_day": round(kwh_day, 0),
            "potential_rm_full_day": round(kwh_day * RM_PER_KWH, 0),
        },
    }
