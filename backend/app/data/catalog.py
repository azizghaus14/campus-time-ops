"""Room catalogue + group-size mocks (APU's rooms/staff feeds are auth-protected, so these are seeded mocks).

Heuristics (BUILD_PROMPT §4.3): auditorium 250-400, classroom 40-80, Tech Lab 30-45, specialist lab 20-30,
discussion 8-12, online = unlimited. Seeded per room name -> stable regardless of iteration order.
"""
from __future__ import annotations

import hashlib
import random
import re

from ..domain import Room

SPECIALIST_HINTS = ("LAB", "STUDIO", "WORKSHOP", "SUITE", "CADCAM", "GREENSCREEN", "TRADING", "CISCO")


def _rng(key: str) -> random.Random:
    return random.Random(int(hashlib.sha256(("campus-time-ops:" + key).encode()).hexdigest(), 16) % (2**32))


def classify_room(name: str) -> tuple[str, str, int | None]:
    """-> (type, block, floor)"""
    n = name.upper()
    if n.startswith("ONLMCO") or n.startswith("ONLINE"):
        return "online", "ONLINE", None
    if n.startswith("AUDITORIUM"):
        m = re.search(r"BLOCK ([A-Z])", n)
        f = re.search(r"LEVEL (\d+)", n)
        return "auditorium", (m.group(1) if m else "B"), (int(f.group(1)) if f else None)
    if n.startswith("TECH LAB"):
        f = re.search(r"TECH LAB (\d+)-", n)
        if any(h in n for h in ("SUITE", "GREENSCREEN", "TRADING", "CISCO")):
            return "specialist_lab", "TL", (int(f.group(1)) if f else None)
        return "lab", "TL", (int(f.group(1)) if f else None)
    if n.startswith("DISCUSSION"):
        return "discussion", "LIB", 4
    if n.startswith("CULINARY"):
        return "culinary", "CUL", None
    if n.startswith("PRESENTATION"):
        return "presentation", "CYB", None
    m = re.match(r"^([A-Z])-(\d{2})-", n)
    if m:
        block, floor = m.group(1), int(m.group(2))
        rest = n[len(m.group(0)):]
        if any(h in rest for h in SPECIALIST_HINTS) or "(" in rest:
            return "specialist_lab", block, floor
        if not re.match(r"^\d{2}$", rest.strip()):
            return "specialist_lab", block, floor
        return "classroom", block, floor
    return "classroom", "X", None


CAPACITY_RANGES = {
    "auditorium": (250, 400),
    "classroom": (40, 80),
    "lab": (30, 45),
    "specialist_lab": (20, 30),
    "discussion": (8, 12),
    "culinary": (20, 30),
    "presentation": (20, 40),
    "online": (0, 0),
}


def build_room(name: str) -> Room:
    rtype, block, floor = classify_room(name)
    lo, hi = CAPACITY_RANGES[rtype]
    cap = _rng(name).randint(lo, hi) if hi else 0
    if rtype == "classroom":
        cap = int(round(cap / 5.0) * 5)
    return Room(
        name=name,
        type=rtype,
        capacity=cap,
        block=block,
        floor=floor,
        online=rtype == "online",
        air_conditioned=rtype != "online",
    )


def group_size(intake: str, grouping: str) -> int:
    return _rng(f"group:{intake}|{grouping}").randint(15, 60)


def school_of(class_code: str) -> str:
    return class_code.split("___")[0] if "___" in class_code else "OTHER"


SCHOOL_NAMES = {
    "SAFI": "School of Accounting, Finance & Investment (mock label)",
    "MOR": "School of Business & Management (mock label)",
    "CSSE": "School of Computing - Software Engineering (mock label)",
    "NSF": "School of Computing - Networks & Security (mock label)",
    "TM": "School of Technology & Media (mock label)",
    "SOGS": "Graduate School (mock label)",
    "SOMAQS": "School of Media, Arts & Design (mock label)",
    "MTS": "Mathematical & Technology Studies (mock label)",
    "SOE": "School of Engineering (mock label)",
    "APP": "School of Psychology (mock label)",
    "MEE": "Mechatronic & Electrical Eng. (mock label)",
    "MAV": "Media, Animation & VFX (mock label)",
}
