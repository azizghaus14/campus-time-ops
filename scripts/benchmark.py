#!/usr/bin/env python3
"""Measure solver metrics from the system for docs/METRICS.md (writes docs/metrics.json)."""
from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.store import JsonStore, set_store  # noqa: E402
from app.services.workspace import LocalWorkspace, set_workspace  # noqa: E402

set_store(JsonStore(Path(tempfile.mkdtemp())))
set_workspace(LocalWorkspace(Path(tempfile.mkdtemp())))

from app.data.loader import get_dataset  # noqa: E402
from app.services import proposals, replan  # noqa: E402

ds = get_dataset()
results = []


def run(label, dtype, scope, window=None, execute=False):
    t = time.perf_counter()
    d = replan.create_disruption(dtype, scope, window, label)
    p = replan.plan_replan(d["id"])
    el = time.perf_counter() - t
    row = {"case": label, "type": dtype, "sessions": d["impact"]["sessions"], "intake_groups": d["impact"]["intake_groups"],
           "students": d["impact"]["students"], "solve_s": p["stats"]["total_s"], "end_to_end_s": round(el, 3),
           "status": p["stats"]["status"], "substituted": p["summary"]["substituted"], "rescheduled": p["summary"]["rescheduled"], "physical": p["summary"]["placed_physical"], "online": p["summary"]["placed_online"],
           "unresolved": p["summary"]["unresolved"], "room_only": p["summary"]["room_only_changes"],
           "clash_free": p["summary"]["clash_check"]["passed"]}
    if execute:
        proposals.approve_proposal(p["id"], "benchmark")
        ex = proposals.execute_proposal(p["id"])["execution"]["actions"]
        row["actions"] = ex
        from app.data.loader import reset_dataset

        reset_dataset()
    results.append(row)
    print(json.dumps(row))


# sick lecturers: the 10 busiest lecturers on Fri 13 Nov
fri = date(2026, 11, 13)
lects = Counter(ds.sessions[i].lecturer_id for i in ds.by_date[fri]).most_common(10)
for lid, _ in lects:
    run(f"sick {lid} Fri 13", "LECTURER_UNAVAILABLE", {"lecturer_id": lid}, {"start": "2026-11-13", "end": "2026-11-13"}, execute=lid == lects[0][0])
# rooms: 5 busiest classrooms closed Mon-Fri
busy_rooms = Counter(ds.sessions[i].room for d in ds.dates for i in ds.by_date[d] if ds.rooms[ds.sessions[i].room].type == "classroom").most_common(5)
for r, _ in busy_rooms:
    run(f"room {r} closed to Fri 20", "ROOM_UNAVAILABLE", {"rooms": [r]}, {"start": "2026-11-16", "end": "2026-11-20"})
for d in ["2026-11-16", "2026-11-17", "2026-11-18"]:
    run(f"campus holiday {d}", "HOLIDAY", {"date": d}, None, execute=d == "2026-11-16")

summary = {}
for t in ("LECTURER_UNAVAILABLE", "ROOM_UNAVAILABLE", "HOLIDAY"):
    rs = [r for r in results if r["type"] == t]
    summary[t] = {"cases": len(rs), "median_solve_s": round(statistics.median(r["solve_s"] for r in rs), 3),
                  "max_solve_s": max(r["solve_s"] for r in rs), "sessions_total": sum(r["sessions"] for r in rs),
                  "physical_share": round(sum(r["physical"] for r in rs) / max(1, sum(r["sessions"] for r in rs)), 3),
                  "online_share": round(sum(r["online"] for r in rs) / max(1, sum(r["sessions"] for r in rs)), 3),
                  "unresolved_share": round(sum(r["unresolved"] for r in rs) / max(1, sum(r["sessions"] for r in rs)), 3),
                  "substituted": sum(r["substituted"] for r in rs), "rescheduled": sum(r["rescheduled"] for r in rs),
                  "all_clash_free": all(r["clash_free"] for r in rs)}
out = {"measured_at": time.strftime("%Y-%m-%d %H:%M"), "snapshot": ds.meta.get("snapshot_file"), "cases": results, "summary": summary}
(ROOT / "docs" / "metrics.json").write_text(json.dumps(out, indent=1))
print(json.dumps(summary, indent=1))
