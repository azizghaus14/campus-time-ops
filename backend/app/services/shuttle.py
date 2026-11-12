"""Last campus shuttle per day (APU Campus Connect PDF, effective 22 Oct 2026). Drives rule R-SHUTTLE."""
from __future__ import annotations

from datetime import date
from typing import Optional

from ..config import settings
from ..data.loader import get_dataset
from .holidays import holiday_on


def _to_min(t: Optional[str]) -> Optional[int]:
    if not t:
        return None
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def last_shuttle_min(d: date) -> Optional[int]:
    """Minutes since midnight of the last departure from campus on the rule stop (LRT, serves all students).
    None = no service that day."""
    sh = get_dataset().shuttle
    if d.strftime("%a").upper() not in sh["service_days"] or holiday_on(d):
        return None
    stop = next(s for s in sh["stops"] if s["code"] == sh.get("campus_rule_stop", "LRT"))
    t = stop["last_limited"] if settings.shuttle_include_limited and stop.get("last_limited") else stop["last_regular"]
    return _to_min(t)


def latest_end_for_physical(d: date) -> Optional[int]:
    """A physical make-up class must END at least SHUTTLE_BUFFER_MIN before the last shuttle."""
    last = last_shuttle_min(d)
    return None if last is None else last - settings.shuttle_buffer_min


def get_last_shuttle(date_str: str) -> dict:
    from .errors import require

    try:
        d = date.fromisoformat(date_str)
    except Exception:
        require(False, "BAD_DATE", "date must be YYYY-MM-DD", got=date_str)
    sh = get_dataset().shuttle
    last = last_shuttle_min(d)
    per_stop = []
    for s in sh["stops"]:
        per_stop.append(
            {
                "stop": s["name"],
                "code": s["code"],
                "last_regular": s["last_regular"],
                "last_limited_space": s.get("last_limited"),
                "verify": s.get("verify", False),
            }
        )
    return {
        "date": d.isoformat(),
        "day": d.strftime("%a").upper(),
        "service": last is not None,
        "rule_stop": sh.get("campus_rule_stop", "LRT"),
        "last_departure": f"{last // 60:02d}:{last % 60:02d}" if last is not None else None,
        "latest_class_end": (
            f"{(last - settings.shuttle_buffer_min) // 60:02d}:{(last - settings.shuttle_buffer_min) % 60:02d}"
            if last is not None
            else None
        ),
        "rule": "R-SHUTTLE: physical make-up classes end >= %d min before the last regular shuttle" % settings.shuttle_buffer_min,
        "stops": per_stop,
        "source": sh["source"],
    }
