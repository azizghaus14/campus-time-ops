"""Decomposition for very large disruptions: solve one model if it fits the time budget, otherwise split by school
(faculty) and solve sequentially, each chunk respecting earlier assignments (via the Context overlay)."""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import replace

from ..data.loader import Dataset
from .model import Context, SolveRequest, SolveResult, solve

SINGLE_MODEL_MAX_SESSIONS = 900


def solve_with_decomposition(req: SolveRequest, ds: Dataset, force_split: bool = False) -> SolveResult:
    if not force_split and len(req.sessions) <= SINGLE_MODEL_MAX_SESSIONS:
        res = solve(req, ds)
        if res.stats["engine"] == "cp-sat":
            res.stats["decomposition"] = "single-model"
            return res
    t0 = time.perf_counter()
    by_school: dict[str, list] = defaultdict(list)
    for s in req.sessions:
        by_school[s.school].append(s)
    # biggest / most constrained schools first
    chunks = sorted(by_school.values(), key=lambda ss: -sum(len(s.groups) for s in ss))
    ctx = Context(ds, {s.id for s in req.sessions})
    total = len(req.sessions)
    assignments, unresolved, elims, chunk_stats = {}, {}, {}, []
    lect_of = lambda s: req.substitutes.get(s.id) or req.substitutes.get("*") or s.lecturer_id  # noqa: E731
    for ss in chunks:
        remaining = max(0.5, req.time_limit - (time.perf_counter() - t0))
        budget = max(0.3, remaining * len(ss) / max(1, total))
        sub = replace(req, sessions=ss, time_limit=budget)
        r = solve(sub, ds, ctx)
        for sid, c in r.assignments.items():
            ctx.commit(ds.sessions[sid], c, lect_of(ds.sessions[sid]))
        assignments.update(r.assignments)
        unresolved.update(r.unresolved)
        elims.update(r.eliminations)
        chunk_stats.append({"school": ss[0].school, "sessions": len(ss), "status": r.stats["status"], "s": r.stats["total_s"]})
        total -= len(ss)
    stats = {
        "engine": "cp-sat",
        "decomposition": f"by-school ({len(chunks)} chunks)",
        "status": "FEASIBLE" if all(c["status"] in ("OPTIMAL", "FEASIBLE") for c in chunk_stats) else "PARTIAL",
        "objective": None,
        "sessions": len(req.sessions),
        "chunks": chunk_stats,
        "total_s": round(time.perf_counter() - t0, 3),
        "time_limit_s": req.time_limit,
        "seed": req.seed,
    }
    return SolveResult(assignments, unresolved, stats, elims)
