"""Soft-objective weights and cost terms (minimised). Integers because CP-SAT objectives are integral."""
from __future__ import annotations

from datetime import date

from ..config import EVENING_START_MIN, STANDARD_STARTS

W = {
    "day_distance": 6,  # per calendar day away from the original date (prefer sooner / closest)
    "nonstandard_start": 15,  # R-GRID
    "different_time_of_day": 4,  # keep the students' routine if possible
    "evening": 30,  # R-EVENING
    "same_room": 0,
    "same_block": 8,
    "other_room": 20,
    "capacity_waste": 4,  # x (1 - fill ratio); prefer right-sized rooms
    "day_over_6h": 18,  # per affected group (capped), R-LOAD
    "consecutive_4plus": 12,  # per affected group (capped), R-LOAD
    "online": 400,  # R-ONLINE: heavy
    "unresolved": 10_000,  # R-UNRESOLVED: heaviest
}

LOAD_GROUP_CAP = 4


def time_cost(orig_date: date, orig_start: int, d: date, start: int) -> tuple[int, list[str]]:
    c, why = 0, []
    dist = abs((d - orig_date).days)
    c += W["day_distance"] * dist
    if start not in STANDARD_STARTS:
        c += W["nonstandard_start"]
        why.append("non-standard start")
    if start != orig_start:
        c += W["different_time_of_day"]
    if start >= EVENING_START_MIN:
        c += W["evening"]
        why.append("evening")
    return c, why


def room_cost(orig_room: str, orig_block: str, room: str, block: str, capacity: int, headcount: int) -> tuple[int, str]:
    if room == orig_room:
        tier, label = W["same_room"], "same room"
    elif block == orig_block:
        tier, label = W["same_block"], "same block"
    else:
        tier, label = W["other_room"], "different block"
    waste = 0
    if capacity:
        waste = int(round(W["capacity_waste"] * (1 - min(1.0, headcount / capacity))))
    return tier + waste, label
