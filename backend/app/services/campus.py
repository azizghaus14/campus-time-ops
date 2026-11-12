"""Schematic 3D campus model for the dashboard map.

APU does not publish building geometry, so the layout is GENERATED from room codes (block-floor-room, e.g. B-04-03):
one building per block (A, B, C, D, E, S) plus Tech Labs, Library, Cyber range and Culinary; floors from the code;
rooms laid out in a grid per floor. Positions are a schematic site plan, not to scale (labelled in the UI).
The day endpoint returns every room's sessions for a date so the client can scrub through time without refetching.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta
from functools import lru_cache

from ..config import DAY_END_MIN, DAY_START_MIN
from ..data.loader import get_dataset
from ..domain import hhmm
from .store import get_store
from .timetable import parse_date

SITE = {  # building id -> (name, x, z)
    "B": ("Block B", 0, 0), "A": ("Block A", -42, -14), "C": ("Block C", -42, 24), "D": ("Block D", 42, -16),
    "E": ("Block E", 44, 24), "S": ("Block S", 0, 44), "TL": ("Tech Labs", 0, -42), "LIB": ("Library", -40, -48),
    "CYB": ("Cyber Range", 40, -50), "CUL": ("Culinary", -34, 56),
}
CELL = 3.4
FLOOR_H = 2.6


def _building_of(r) -> str:
    if r.type == "auditorium":
        return r.block if r.block in SITE else "B"
    if r.block in SITE:
        return r.block
    return "B"


@lru_cache(maxsize=1)
def _layout_cached(n_rooms: int) -> dict:
    ds = get_dataset()
    floors: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for r in ds.rooms.values():
        if r.online:
            continue
        floors[_building_of(r)][r.floor or 1].append(r)
    buildings = []
    for bid, (name, x, z) in SITE.items():
        if bid not in floors:
            continue
        fl = floors[bid]
        widest = max(len(v) for v in fl.values())
        cols = max(2, math.ceil(math.sqrt(widest * 1.7)))
        rows = max(1, math.ceil(widest / cols))
        w, d = cols * CELL + 1.2, rows * CELL + 1.2
        levels = sorted(fl)
        out_floors = []
        for i, lv in enumerate(levels):
            rs = sorted(fl[lv], key=lambda r: r.name)
            out_floors.append({
                "level": lv, "index": i, "y": i * FLOOR_H,
                "rooms": [{"name": r.name, "type": r.type, "capacity": r.capacity,
                           "x": round(-w / 2 + 0.6 + CELL / 2 + (k % cols) * CELL, 2),
                           "z": round(-d / 2 + 0.6 + CELL / 2 + (k // cols) * CELL, 2)} for k, r in enumerate(rs)],
            })
        buildings.append({"id": bid, "name": name, "x": x, "z": z, "w": round(w, 2), "d": round(d, 2), "height": len(levels) * FLOOR_H,
                          "floors": out_floors, "rooms": sum(len(v) for v in fl.values())})
    return {"buildings": buildings, "cell": CELL, "floor_height": FLOOR_H,
            "note": "Schematic layout generated from room codes - not to scale; APU building geometry is not public."}


def layout() -> dict:
    ds = get_dataset()
    out = dict(_layout_cached(len(ds.rooms)))
    out["dates"] = [d.isoformat() for d in ds.dates if d.weekday() < 5 and len(ds.by_date.get(d, [])) > 50]
    return out


def day(date_str: str) -> dict:
    ds = get_dataset()
    d = parse_date(date_str)
    st = get_store()
    affected: set[str] = set()
    pending_to: dict[str, list] = defaultdict(list)
    disruptions = []
    for dis in st.list("disruptions"):
        if dis.get("status") in ("OPEN", "PLANNED"):
            ids = [i for i in dis["affected_session_ids"] if i in ds.sessions and ds.sessions[i].date == d]
            affected.update(ids)
            if ids or dis["type"] == "HOLIDAY":
                disruptions.append({"id": dis["id"], "type": dis["type"], "scope": dis["scope"], "sessions_today": len(ids),
                                    "proposal_id": dis.get("latest_proposal_id")})
            pid = dis.get("latest_proposal_id")
            p = st.get("proposals", pid) if pid else None
            if p and p["status"] == "DRAFT":
                for m in p["moves"]:
                    if m["to"]["date"] == d.isoformat() and m["type"] != "SUBSTITUTE":
                        s0 = int(m["to"]["start"][11:13]) * 60 + int(m["to"]["start"][14:16])
                        e0 = int(m["to"]["end"][11:13]) * 60 + int(m["to"]["end"][14:16])
                        pending_to[m["to"]["room"]].append({"s": s0, "e": e0, "module": m["module_name"], "lecturer": m["lecturer_id"],
                                                            "groups": len(m["affected_groups"]), "students": m["students"], "pending": True,
                                                            "proposal_id": pid})
    rooms_out = {}
    online_by_hour = defaultdict(int)
    for name, r in ds.rooms.items():
        items = []
        for sid in ds.by_room.get(name, []):
            s = ds.sessions[sid]
            if s.date != d:
                continue
            if r.online:
                online_by_hour[s.start_min // 60] += 1
                continue
            items.append({"s": s.start_min, "e": s.end_min, "sid": sid, "module": s.module_name, "lecturer": s.lecturer_id,
                          "groups": len(s.groups), "students": ds.session_students(s), "moved": bool(s.moved_by),
                          "affected": sid in affected, "time": f"{hhmm(s.start_min)}-{hhmm(s.end_min)}"})
        items += pending_to.get(name, [])
        if not r.online:
            busy = sum(i["e"] - i["s"] for i in items if not i.get("pending"))
            rooms_out[name] = {"sessions": sorted(items, key=lambda i: i["s"]), "util": round(min(1.0, busy / (DAY_END_MIN - DAY_START_MIN)), 3)}
    # week utilisation for the heat layer
    wk0 = d - timedelta(days=d.weekday())
    days = [wk0 + timedelta(days=i) for i in range(5)]
    week = {}
    for name, r in ds.rooms.items():
        if r.online:
            continue
        busy = sum(ds.room_busy.busy_minutes(name, x) for x in days)
        week[name] = round(min(1.0, busy / (5 * (DAY_END_MIN - DAY_START_MIN))), 3)
    for k, v in rooms_out.items():
        v["week_util"] = week.get(k, 0)
    return {"date": d.isoformat(), "rooms": rooms_out, "disruptions": disruptions,
            "online_by_hour": [{"hour": h, "sessions": online_by_hour.get(h, 0)} for h in range(8, 21)],
            "totals": {"sessions": sum(len(v["sessions"]) for v in rooms_out.values()), "affected": len(affected)}}
