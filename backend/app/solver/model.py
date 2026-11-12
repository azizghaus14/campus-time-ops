"""CP-SAT re-planning model.

Time: 15-minute ticks 08:30-21:00 MYT (start times are drawn from the standard grid + the original start, all tick-aligned).
Variables: x[c] for every *pre-filtered* candidate c = (session, day, start, room|ONLINE); u[s] = unresolved.
Hard constraints (R-* ids in grounding/campus_ops_policy.md):
  exactly one of {candidates, unresolved} per session
  candidates are generated only if: working day, not holiday (R-HOL/R-WEEKEND), notice (R-NOTICE), shuttle (R-SHUTTLE),
      duration kept (R-DURATION), lecturer free + not blocked (R-CLASH-LECT), all groups free (R-CLASH-GROUP),
      room free + not blocked + capacity + type (R-ROOM-*), w.r.t. the FIXED timetable
  pairwise between moved sessions: AtMostOne over every room / lecturer / group time point
Objective: weighted soft costs (objectives.py), online heavily, unresolved most heavily.
"""
from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from ortools.sat.python import cp_model

from ..config import DAY_END_MIN, DAY_START_MIN, EVENING_START_MIN, STANDARD_STARTS, TICK_MIN, settings
from ..data.indexes import BusyIndex
from ..data.loader import Dataset
from ..domain import Session, hhmm
from ..services.shuttle import latest_end_for_physical
from .objectives import LOAD_GROUP_CAP, W, room_cost, time_cost

COMPATIBLE = {
    "classroom": ("classroom",),
    "lab": ("lab",),
    "auditorium": ("auditorium", "classroom"),
    "discussion": ("discussion", "classroom"),
    "presentation": ("presentation", "classroom"),
    "specialist_lab": (),  # same room only (R-ROOM-TYPE)
    "culinary": (),
    "online": (),
}

Interval = tuple[date, int, int]


@dataclass
class SolveRequest:
    sessions: list[Session]
    days: list[date]
    earliest: datetime
    blocked_lecturers: dict[str, list[Interval]] = field(default_factory=dict)
    blocked_rooms: dict[str, list[Interval]] = field(default_factory=dict)
    allow_online: bool = True
    allow_same_slot: bool = False  # e.g. ROOM_UNAVAILABLE: original time, different room (exempt from notice)
    pins: dict[str, dict] = field(default_factory=dict)
    substitutes: dict[str, str] = field(default_factory=dict)
    preferred_starts: Optional[list[int]] = None
    max_moves_per_group_per_week: Optional[int] = None
    time_limit: float = 3.0
    seed: int = 42
    max_time_cands: int = 30
    max_room_cands: int = 8
    online_time_cands: int = 4
    workers: int = 8


@dataclass
class Cand:
    sid: str
    day: date
    start: int
    end: int
    room: str
    online: bool
    cost: int
    notes: list[str]
    room_label: str = ""


@dataclass
class SolveResult:
    assignments: dict[str, Cand]
    unresolved: dict[str, dict]
    stats: dict
    eliminations: dict[str, dict]


def _blocked(lst: list[Interval], d: date, s: int, e: int) -> bool:
    return any(bd == d and bs < e and s < be for bd, bs, be in lst)


class Context:
    """Fixed timetable (dataset indexes minus the sessions being moved) + overlay of already-placed moves."""

    def __init__(self, ds: Dataset, moving_ids: set[str]) -> None:
        self.ds = ds
        self.ignore = moving_ids
        self.o_room, self.o_lect, self.o_group = BusyIndex(), BusyIndex(), BusyIndex()
        self._free_rooms_cache: dict[tuple, list] = {}

    def room_free(self, room: str, d: date, s: int, e: int) -> bool:
        return self.ds.room_busy.is_free(room, d, s, e, self.ignore) and self.o_room.is_free(room, d, s, e)

    def lect_free(self, lect: str, d: date, s: int, e: int) -> bool:
        return self.ds.lect_busy.is_free(lect, d, s, e, self.ignore) and self.o_lect.is_free(lect, d, s, e)

    def group_conflict(self, groups, d: date, s: int, e: int) -> Optional[tuple]:
        for g in groups:
            if not (self.ds.group_busy.is_free(g, d, s, e, self.ignore) and self.o_group.is_free(g, d, s, e)):
                return g
        return None

    def group_day_minutes(self, g, d: date) -> int:
        return self.ds.group_busy.busy_minutes(g, d, self.ignore) + self.o_group.busy_minutes(g, d)

    def group_day_intervals(self, g, d: date) -> list[tuple[int, int]]:
        a = [(s, e) for s, e, sid in self.ds.group_busy.intervals(g, d) if sid not in self.ignore]
        b = [(s, e) for s, e, _ in self.o_group.intervals(g, d)]
        return sorted(a + b)

    def free_rooms(self, d: date, s: int, e: int) -> list[str]:
        key = (d, s, e)
        if key not in self._free_rooms_cache:
            self._free_rooms_cache[key] = [r for r in self.ds.rooms if r != "ONLINE" and self.room_free(r, d, s, e)]
        return self._free_rooms_cache[key]

    def commit(self, sess: Session, c: Cand, lect: str) -> None:
        if c.room != "ONLINE":
            self.o_room.add(c.room, c.day, c.start, c.end, sess.id)
        self.o_lect.add(lect, c.day, c.start, c.end, sess.id)
        for g in sess.groups:
            self.o_group.add(g, c.day, c.start, c.end, sess.id)
        self._free_rooms_cache = {k: v for k, v in self._free_rooms_cache.items() if k[0] != c.day}


def _consecutive_after(intervals: list[tuple[int, int]], s: int, e: int) -> int:
    ivs = sorted(intervals + [(s, e)])
    best = run = 1
    for (a1, b1), (a2, b2) in zip(ivs, ivs[1:]):
        run = run + 1 if a2 - b1 <= 30 else 1
        best = max(best, run)
    return best


def _period_ok(start: int, period: Optional[str]) -> bool:
    if not period:
        return True
    p = period.lower()
    if p == "morning":
        return start < 12 * 60
    if p == "afternoon":
        return 12 * 60 <= start < EVENING_START_MIN
    if p == "evening":
        return start >= EVENING_START_MIN
    return True


def generate_candidates(req: SolveRequest, ctx: Context, sess: Session, headcount: int) -> tuple[list[Cand], dict]:
    ds = ctx.ds
    room = ds.rooms[sess.room]
    is_online = room.online
    lect = req.substitutes.get(sess.id) or req.substitutes.get("*") or sess.lecturer_id
    pin = req.pins.get(sess.id, {})
    elim: dict[str, Counter] = defaultdict(Counter)

    starts = list(req.preferred_starts or STANDARD_STARTS)
    if sess.start_min not in starts and (sess.start_min - DAY_START_MIN) % TICK_MIN == 0:
        starts.append(sess.start_min)
    if pin.get("start") is not None:
        starts = [int(pin["start"])]

    days = list(req.days)
    if req.allow_same_slot and sess.date not in days:
        days = [sess.date] + days
    if pin.get("date"):
        days = [d for d in days if d.isoformat() == pin["date"]]

    time_cands: list[tuple[int, date, int, int, list[str]]] = []
    for d in days:
        latest_phys = latest_end_for_physical(d)
        for st in starts:
            en = st + sess.duration
            same_slot = d == sess.date and st == sess.start_min
            if en > DAY_END_MIN or st < DAY_START_MIN:
                elim[d.isoformat()]["outside teaching day"] += 1
                continue
            if not _period_ok(st, pin.get("period")):
                continue
            if same_slot and not req.allow_same_slot and lect == sess.lecturer_id:
                continue
            start_dt = datetime(d.year, d.month, d.day, st // 60, st % 60, tzinfo=req.earliest.tzinfo)
            if not same_slot and start_dt < req.earliest:
                elim[d.isoformat()]["notice period (R-NOTICE)"] += 1
                continue
            if _blocked(req.blocked_lecturers.get(lect, []), d, st, en):
                elim[d.isoformat()]["lecturer unavailable"] += 1
                continue
            if not same_slot and not ctx.lect_free(lect, d, st, en):
                elim[d.isoformat()]["lecturer busy (R-CLASH-LECT)"] += 1
                continue
            if not same_slot:
                g = ctx.group_conflict(sess.groups, d, st, en)
                if g:
                    elim[d.isoformat()][f"group clash (R-CLASH-GROUP)"] += 1
                    continue
            phys_ok = is_online or (latest_phys is not None and en <= latest_phys)
            c, notes = time_cost(sess.date, sess.start_min, d, st)
            # R-LOAD
            over, consec = 0, 0
            for g in sess.groups[:40]:
                if not same_slot:
                    if ctx.group_day_minutes(g, d) + sess.duration > 360:
                        over += 1
                    if _consecutive_after(ctx.group_day_intervals(g, d), st, en) >= 4:
                        consec += 1
            if over:
                c += W["day_over_6h"] * min(over, LOAD_GROUP_CAP)
                notes.append(f"{over} group(s) > 6h that day")
            if consec:
                c += W["consecutive_4plus"] * min(consec, LOAD_GROUP_CAP)
                notes.append(f"{consec} group(s) 4+ in a row")
            if not phys_ok:
                elim[d.isoformat()]["after last shuttle (R-SHUTTLE)"] += 1
                notes = notes + ["shuttle:online-only"]
            time_cands.append((c, d, st, en, notes))

    time_cands.sort(key=lambda t: (t[0], t[1], t[2]))
    phys_tc = [t for t in time_cands if "shuttle:online-only" not in t[4]][: req.max_time_cands]

    cands: list[Cand] = []
    orig_block = room.block
    for c, d, st, en, notes in phys_tc:
        same_slot = d == sess.date and st == sess.start_min
        if is_online:
            own_ok = (
                not same_slot
                and ctx.room_free(sess.room, d, st, en)
                and not _blocked(req.blocked_rooms.get(sess.room, []), d, st, en)
            )
            if own_ok:
                cands.append(Cand(sess.id, d, st, en, sess.room, False, c, notes, "same online room"))
            else:
                cands.append(Cand(sess.id, d, st, en, "ONLINE", False, c + 1, notes, "online (virtual room)"))
            continue
        types = COMPATIBLE.get(room.type, ())
        pool = []
        free = ctx.free_rooms(d, st, en)
        free_set = set(free)
        if sess.room in free_set and not _blocked(req.blocked_rooms.get(sess.room, []), d, st, en) and not same_slot:
            pool.append(sess.room)
        for rn in free:
            if rn == sess.room:
                continue
            r = ds.rooms[rn]
            if r.type not in types or r.capacity < headcount:
                continue
            if _blocked(req.blocked_rooms.get(rn, []), d, st, en):
                continue
            pool.append(rn)
        if pin.get("room"):
            pool = [p for p in pool if p == pin["room"]]
        if not pool:
            elim[d.isoformat()]["no free room of right type/capacity (R-ROOM-*)"] += 1
        scored = []
        for rn in pool:
            r = ds.rooms[rn]
            rc, lab = room_cost(sess.room, orig_block, rn, r.block, r.capacity, headcount)
            scored.append((rc, rn, lab))
        scored.sort()
        for rc, rn, lab in scored[: req.max_room_cands]:
            cands.append(Cand(sess.id, d, st, en, rn, False, c + rc, notes, lab))

    if req.allow_online and not is_online and not pin.get("room"):
        online_tc = [t for t in time_cands if not (t[1] == sess.date and t[2] == sess.start_min)][: req.online_time_cands]
        for c, d, st, en, notes in online_tc:
            cands.append(Cand(sess.id, d, st, en, "ONLINE", True, c + W["online"], [n for n in notes if not n.startswith("shuttle:")], "online fallback"))
    if pin.get("online") is True:
        cands = [x for x in cands if x.room == "ONLINE"]
    elim_out = {k: dict(v) for k, v in elim.items()}
    return cands, {"by_day": elim_out, "time_candidates": len(time_cands)}


def _greedy(req: SolveRequest, ctx_factory, sessions: list[Session], cands: dict[str, list[Cand]], lect_of) -> dict[str, Cand]:
    ctx: Context = ctx_factory()
    chosen: dict[str, Cand] = {}
    order = sorted(sessions, key=lambda s: (len(cands[s.id]) or 10**6, -len(s.groups), s.id))
    for s in order:
        for c in sorted(cands[s.id], key=lambda c: (c.cost, c.day, c.start, c.room)):
            if c.room != "ONLINE" and not ctx.o_room.is_free(c.room, c.day, c.start, c.end):
                continue
            if not ctx.o_lect.is_free(lect_of(s), c.day, c.start, c.end):
                continue
            if any(not ctx.o_group.is_free(g, c.day, c.start, c.end) for g in s.groups):
                continue
            chosen[s.id] = c
            ctx.commit(s, c, lect_of(s))
            break
    return chosen


def solve(req: SolveRequest, ds: Dataset, ctx: Optional[Context] = None) -> SolveResult:
    t0 = time.perf_counter()
    moving_ids = {s.id for s in req.sessions}
    ctx = ctx or Context(ds, moving_ids)
    lect_of = lambda s: req.substitutes.get(s.id) or req.substitutes.get("*") or s.lecturer_id  # noqa: E731

    cands: dict[str, list[Cand]] = {}
    elims: dict[str, dict] = {}
    for s in req.sessions:
        cands[s.id], elims[s.id] = generate_candidates(req, ctx, s, ds.session_students(s))
    t_gen = time.perf_counter() - t0

    m = cp_model.CpModel()
    xs: dict[int, cp_model.IntVar] = {}
    flat: list[Cand] = []
    us: dict[str, cp_model.IntVar] = {}
    res_points: dict[tuple, list[tuple[int, int, int]]] = defaultdict(list)  # (kind,key,day) -> (start,end,var_idx)
    week_vars: dict[tuple, list[int]] = defaultdict(list)
    for s in req.sessions:
        vs = []
        for c in cands[s.id]:
            i = len(flat)
            flat.append(c)
            xs[i] = m.NewBoolVar(f"x{i}")
            vs.append(xs[i])
            if c.room != "ONLINE":
                res_points[("room", c.room, c.day)].append((c.start, c.end, i))
            res_points[("lect", lect_of(s), c.day)].append((c.start, c.end, i))
            for g in s.groups:
                res_points[("group", g, c.day)].append((c.start, c.end, i))
                if req.max_moves_per_group_per_week:
                    week_vars[(g, c.day.isocalendar()[1])].append(i)
        us[s.id] = m.NewBoolVar(f"u_{s.id}")
        m.AddExactlyOne(vs + [us[s.id]])

    n_cons = 0
    for key, items in res_points.items():
        if len(items) < 2:
            continue
        sessions_in = {flat[i].sid for _, _, i in items}
        if len(sessions_in) < 2:
            continue
        for p in sorted({st for st, _, _ in items}):
            cover = [xs[i] for st, en, i in items if st <= p < en]
            if len(cover) > 1 and len({flat[i].sid for st, en, i in items if st <= p < en}) > 1:
                m.AddAtMostOne(cover)
                n_cons += 1
    if req.max_moves_per_group_per_week:
        for key, idx in week_vars.items():
            if len({flat[i].sid for i in idx}) > req.max_moves_per_group_per_week:
                m.Add(sum(xs[i] for i in idx) <= req.max_moves_per_group_per_week)

    m.Minimize(sum(flat[i].cost * v for i, v in xs.items()) + sum(W["unresolved"] * u for u in us.values()))

    # greedy warm start (also the fallback if CP-SAT returns no solution in time)
    greedy = _greedy(req, lambda: Context(ds, moving_ids), req.sessions, cands, lect_of)
    gset = {(c.sid, c.day, c.start, c.room) for c in greedy.values()}
    for i, c in enumerate(flat):
        m.AddHint(xs[i], (c.sid, c.day, c.start, c.room) in gset)
    for sid, u in us.items():
        m.AddHint(u, sid not in greedy)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.2, req.time_limit - t_gen)
    solver.parameters.num_workers = req.workers
    solver.parameters.random_seed = req.seed
    t1 = time.perf_counter()
    status = solver.Solve(m)
    t_solve = time.perf_counter() - t1

    assignments: dict[str, Cand] = {}
    used = "cp-sat"
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for i, c in enumerate(flat):
            if solver.BooleanValue(xs[i]):
                assignments[c.sid] = c
    else:
        assignments = greedy
        used = "greedy-fallback"

    unresolved = {}
    for s in req.sessions:
        if s.id not in assignments:
            unresolved[s.id] = _diagnose(s, cands[s.id], elims[s.id])

    stats = {
        "engine": used,
        "status": solver.StatusName(status),
        "objective": int(solver.ObjectiveValue()) if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None,
        "best_bound": int(solver.BestObjectiveBound()) if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None,
        "greedy_placed": len(greedy),
        "sessions": len(req.sessions),
        "variables": len(flat) + len(us),
        "candidates": len(flat),
        "pairwise_constraints": n_cons,
        "candidate_gen_s": round(t_gen, 3),
        "solve_s": round(t_solve, 3),
        "total_s": round(time.perf_counter() - t0, 3),
        "time_limit_s": req.time_limit,
        "workers": req.workers,
        "seed": req.seed,
    }
    return SolveResult(assignments, unresolved, stats, elims)


def _diagnose(s: Session, cands: list[Cand], elim: dict) -> dict:
    tot = Counter()
    for day, c in elim.get("by_day", {}).items():
        tot.update(c)
    if not cands:
        reason = "no feasible slot in horizon: " + ", ".join(f"{k} x{v}" for k, v in tot.most_common(3))
    else:
        reason = "all feasible slots were taken by other moved sessions (capacity of horizon exhausted)"
    return {
        "reason": reason,
        "blocking": dict(tot.most_common(5)),
        "options": ["go online (if not already allowed)", "extend the horizon", "assign a substitute lecturer", "cancel this session"],
    }


def check_no_clashes(ds: Dataset, moves: dict[str, Cand], substitutes: Optional[dict[str, str]] = None) -> list[dict]:
    """Independent post-solve verifier: every moved session vs the whole timetable (fixed + other moves).
    Pre-existing clashes in the feed that don't involve a moved session are ignored."""
    substitutes = substitutes or {}
    moving = set(moves)
    room, lect, grp = BusyIndex(), BusyIndex(), BusyIndex()
    for sid, s in ds.sessions.items():
        if sid in moving:
            continue
        room.add(s.room, s.date, s.start_min, s.end_min, sid)
        lect.add(s.lecturer_id, s.date, s.start_min, s.end_min, sid)
        for g in s.groups:
            grp.add(g, s.date, s.start_min, s.end_min, sid)
    problems = []
    for sid, c in sorted(moves.items(), key=lambda kv: (kv[1].day, kv[1].start, kv[0])):
        s = ds.sessions[sid]
        L = substitutes.get(sid) or substitutes.get("*") or s.lecturer_id
        if c.room != "ONLINE":
            for o in room.conflicts(c.room, c.day, c.start, c.end):
                problems.append({"type": "room", "session": sid, "with": o, "room": c.room})
        for o in lect.conflicts(L, c.day, c.start, c.end):
            problems.append({"type": "lecturer", "session": sid, "with": o, "lecturer": L})
        for g in s.groups:
            for o in grp.conflicts(g, c.day, c.start, c.end):
                problems.append({"type": "group", "session": sid, "with": o, "group": list(g)})
        if c.room != "ONLINE":
            room.add(c.room, c.day, c.start, c.end, sid)
        lect.add(L, c.day, c.start, c.end, sid)
        for g in s.groups:
            grp.add(g, c.day, c.start, c.end, sid)
    return problems


def fmt_slot(d: date, start: int, end: int) -> str:
    return f"{d.strftime('%a %d %b')} {hhmm(start)}-{hhmm(end)}"
