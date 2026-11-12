"""M3: solver properties - no clashes (property test), capacity, holidays, shuttle, determinism, performance."""
import random
import time
from datetime import date, datetime, timedelta

import pytest
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app.config import MYT
from app.data.loader import get_dataset
from app.services import replan
from app.services.holidays import declare_runtime_holiday, holiday_on
from app.services.shuttle import latest_end_for_physical
from app.solver.model import SolveRequest, check_no_clashes, solve

DS = get_dataset()
WEEKDAYS = [d for d in DS.dates if d.weekday() < 5 and d >= date(2026, 11, 13)]
LECTS = sorted(DS.by_lecturer)
PHYS_ROOMS = sorted(r for r, x in DS.rooms.items() if not x.online and r in DS.by_room)


def _validate(p: dict):
    ds = get_dataset()
    assert p["summary"]["clash_check"]["passed"], p["summary"]["clash_check"]
    for m in p["moves"]:
        s = ds.sessions[m["session_id"]]
        to_start = datetime.fromisoformat(m["to"]["start"])
        to_end = datetime.fromisoformat(m["to"]["end"])
        d = to_start.date()
        # duration kept
        assert (to_end - to_start).seconds // 60 == s.duration
        # not on a holiday / weekend
        assert d.weekday() < 5 and holiday_on(d) is None
        room = ds.rooms[m["to"]["room"]]
        if not room.online:
            # capacity respected
            assert room.capacity >= ds.session_students(s)
            # shuttle rule
            latest = latest_end_for_physical(d)
            assert latest is not None and to_end.hour * 60 + to_end.minute <= latest
        # notice period unless the time is unchanged (room swap / substitute lecturer)
        if m["change"] not in ("room-only", "lecturer-only"):
            assert to_start >= datetime(2026, 11, 13, 9, 0, tzinfo=MYT)


@hsettings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.integers(0, 10_000), st.sampled_from(["L", "R"]))
def test_property_no_clash_random_disruptions(seed, kind):
    rng = random.Random(seed)
    d = rng.choice(WEEKDAYS[:6])
    if kind == "L":
        lects = sorted({DS.sessions[i].lecturer_id for i in DS.by_date[d]})
        dis = replan.create_disruption("LECTURER_UNAVAILABLE", {"lecturer_id": rng.choice(lects)}, {"start": d.isoformat(), "end": d.isoformat()})
    else:
        rooms = sorted({DS.sessions[i].room for i in DS.by_date[d] if not DS.rooms[DS.sessions[i].room].online})
        dis = replan.create_disruption("ROOM_UNAVAILABLE", {"rooms": rng.sample(rooms, 2)}, {"start": d.isoformat(), "end": (d + timedelta(days=2)).isoformat()})
    if not dis["impact"]["sessions"]:
        return
    p = replan.plan_replan(dis["id"], {"seed": seed % 7})
    _validate(p)


def test_independent_clash_checker_detects_clash():
    """Sanity: the verifier really catches a planted clash."""
    from app.solver.model import Cand

    ds = get_dataset()
    a = ds.sessions[ds.by_date[WEEKDAYS[0]][0]]
    other = next(ds.sessions[i] for i in ds.by_date[WEEKDAYS[1]] if not ds.rooms[ds.sessions[i].room].online)
    planted = {a.id: Cand(a.id, other.date, other.start_min, other.start_min + a.duration, other.room, False, 0, [])}
    probs = check_no_clashes(ds, planted)
    assert any(p["type"] == "room" for p in probs)


def test_holidays_excluded(fresh_dataset):
    # declare Tue 17 Nov a holiday, then re-plan a Mon 16 lecturer: nothing may land on the 17th
    declare_runtime_holiday(date(2026, 11, 17), "test holiday", "TEST")
    lid = max({DS.sessions[i].lecturer_id for i in DS.by_date[date(2026, 11, 16)]}, key=lambda l: len(DS.by_lecturer[l]))
    dis = replan.create_disruption("LECTURER_UNAVAILABLE", {"lecturer_id": lid}, {"start": "2026-11-16", "end": "2026-11-16"})
    p = replan.plan_replan(dis["id"])
    assert all(m["to"]["date"] != "2026-11-17" for m in p["moves"])
    _validate(p)


def test_shuttle_rule_on_evening_sessions():
    ds = get_dataset()
    ev = [i for i in ds.by_date[date(2026, 11, 16)] if ds.sessions[i].start_min >= 18 * 60 + 45 and not ds.rooms[ds.sessions[i].room].online]
    assert ev, "need a physical evening session on Mon 16"
    s = ds.sessions[ev[0]]
    dis = replan.create_disruption("LECTURER_UNAVAILABLE", {"lecturer_id": s.lecturer_id}, {"start": "2026-11-16", "end": "2026-11-16"})
    p = replan.plan_replan(dis["id"])
    _validate(p)
    for m in p["moves"]:
        if not m["to"]["online"] and m["session_id"] == s.id:
            assert int(m["to"]["end"][11:13]) * 60 + int(m["to"]["end"][14:16]) <= 19 * 60


def test_capacity_respected_for_large_session():
    ds = get_dataset()
    big = max((ds.sessions[i] for i in ds.by_date[date(2026, 11, 16)] if not ds.rooms[ds.sessions[i].room].online),
              key=lambda s: ds.session_students(s))
    dis = replan.create_disruption("ROOM_UNAVAILABLE", {"rooms": [big.room]}, {"start": "2026-11-16", "end": "2026-11-16"})
    p = replan.plan_replan(dis["id"])
    _validate(p)


def test_determinism_with_fixed_seed():
    lid = "SPG"
    outs = []
    for _ in range(2):
        dis = replan.create_disruption("LECTURER_UNAVAILABLE", {"lecturer_id": lid}, {"start": "2026-11-13", "end": "2026-11-13"})
        p = replan.plan_replan(dis["id"], {"seed": 7})
        outs.append([(m["session_id"], m["to"]["start"], m["to"]["room"]) for m in p["moves"]])
    assert outs[0] == outs[1] and outs[0]


def test_campus_holiday_under_10s_and_clash_free():
    t = time.perf_counter()
    dis = replan.create_disruption("HOLIDAY", {"date": "2026-11-16"}, None, "test")
    p = replan.plan_replan(dis["id"])
    elapsed = time.perf_counter() - t
    assert elapsed < 10, elapsed
    assert dis["impact"]["sessions"] >= 300
    assert p["summary"]["share_unresolved"] < 0.05
    _validate(p)


def test_decomposition_path_is_clash_free():
    dis = replan.create_disruption("HOLIDAY", {"date": "2026-11-17"}, None, "test")
    p = replan.plan_replan(dis["id"], {"force_decomposition": True})
    assert p["stats"]["decomposition"].startswith("by-school")
    _validate(p)


def test_edit_pins_move_to_afternoon():
    dis = replan.create_disruption("LECTURER_UNAVAILABLE", {"lecturer_id": "SPG"}, {"start": "2026-11-13", "end": "2026-11-13"})
    p = replan.plan_replan(dis["id"])
    target = p["moves"][0]["session_id"]
    p2 = replan.plan_replan(dis["id"], {"pins": {target: {"period": "afternoon"}}})
    m = next(m for m in p2["moves"] if m["session_id"] == target)
    assert 12 <= int(m["to"]["start"][11:13]) < 18
    assert p2["version"] == 2
    _validate(p2)
