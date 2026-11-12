"""Restore a clean demo state (< 10 s): clear proposals/disruptions/audit/escalations, wipe the outbox, reload data."""
from __future__ import annotations

import shutil
import time

from ..config import settings
from ..data.loader import get_dataset, reset_dataset
from . import holidays
from .store import get_store


def reset_demo() -> dict:
    t0 = time.perf_counter()
    get_store().clear()
    holidays.invalidate()
    if settings.outbox_dir.exists():
        for p in settings.outbox_dir.iterdir():
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
    reset_dataset()
    from . import visa

    visa.reload_students()
    ds = get_dataset()
    return {"ok": True, "sessions": len(ds.sessions), "elapsed_s": round(time.perf_counter() - t0, 2)}
