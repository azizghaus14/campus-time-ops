"""APU 2026 holidays (transcribed from apu.edu.my/node/501) + holidays declared at runtime via HOLIDAY disruptions."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from ..data.loader import get_dataset
from .errors import require
from .store import get_store


_cache: Optional[dict[date, dict]] = None


def _runtime() -> dict[date, dict]:
    global _cache
    if _cache is None:
        _cache = {date.fromisoformat(h["date"]): h for h in get_store().list("runtime_holidays")}
    return _cache


def invalidate() -> None:
    global _cache
    _cache = None


def holiday_on(d: date) -> Optional[dict]:
    ds = get_dataset()
    return _runtime().get(d) or ds.holidays.get(d)


def is_working_day(d: date, allow_saturday: bool = False) -> bool:
    if d.weekday() == 6 or (d.weekday() == 5 and not allow_saturday):
        return False
    return holiday_on(d) is None


def working_days(start: date, n: int, allow_saturday: bool = False, last: Optional[date] = None) -> list[date]:
    out, d = [], start
    guard = 0
    while len(out) < n and guard < 400:
        if last and d > last:
            break
        if is_working_day(d, allow_saturday):
            out.append(d)
        d += timedelta(days=1)
        guard += 1
    return out


def get_holidays(year: int = 2026) -> dict:
    require(2000 <= int(year) <= 2100, "BAD_YEAR", "year must be a 4-digit year")
    ds = get_dataset()
    rt = _runtime()
    items = [
        {"date": d.isoformat(), "name": h["name"], "type": h["type"], "source": "APU Holiday Schedule 2026 [R-HOL]"}
        for d, h in sorted(ds.holidays.items())
        if d.year == int(year)
    ]
    items += [
        {"date": d.isoformat(), "name": h["name"], "type": "declared", "source": f"Declared via {h.get('disruption_id')}"}
        for d, h in sorted(rt.items())
        if d.year == int(year)
    ]
    items.sort(key=lambda x: x["date"])
    return {"year": int(year), "count": len(items), "holidays": items}


def declare_runtime_holiday(d: date, name: str, disruption_id: str) -> None:
    get_store().put(
        "runtime_holidays", d.isoformat(), {"date": d.isoformat(), "name": name, "type": "declared", "disruption_id": disruption_id}
    )
    invalidate()
    get_dataset().__dict__.pop("_occ_cache", None)
