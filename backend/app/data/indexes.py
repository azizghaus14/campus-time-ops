"""Busy-interval indexes per room / group / lecturer per date. Used for O(small) clash checks and to keep the
CP-SAT model small (only candidates that are free w.r.t. the fixed timetable become variables)."""
from __future__ import annotations

from bisect import insort
from collections import defaultdict
from datetime import date
from typing import Hashable, Iterable, Optional


class BusyIndex:
    def __init__(self) -> None:
        self._d: dict[Hashable, dict[date, list[tuple[int, int, str]]]] = defaultdict(lambda: defaultdict(list))

    def add(self, key: Hashable, d: date, start: int, end: int, sid: str) -> None:
        insort(self._d[key][d], (start, end, sid))

    def remove(self, key: Hashable, d: date, sid: str) -> None:
        lst = self._d.get(key, {}).get(d)
        if lst:
            lst[:] = [x for x in lst if x[2] != sid]

    def intervals(self, key: Hashable, d: date) -> list[tuple[int, int, str]]:
        return self._d.get(key, {}).get(d, [])

    def conflicts(
        self, key: Hashable, d: date, start: int, end: int, ignore: Optional[set[str]] = None
    ) -> list[str]:
        out = []
        for s, e, sid in self.intervals(key, d):
            if s >= end:
                break
            if e > start and (ignore is None or sid not in ignore):
                out.append(sid)
        return out

    def is_free(self, key: Hashable, d: date, start: int, end: int, ignore: Optional[set[str]] = None) -> bool:
        for s, e, sid in self.intervals(key, d):
            if s >= end:
                break
            if e > start and (ignore is None or sid not in ignore):
                return False
        return True

    def busy_minutes(self, key: Hashable, d: date, ignore: Optional[set[str]] = None) -> int:
        return sum(e - s for s, e, sid in self.intervals(key, d) if not ignore or sid not in ignore)

    def keys(self) -> Iterable[Hashable]:
        return self._d.keys()


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end
