"""A1: substitute finder never returns a lecturer who has a clash or doesn't teach the module."""
from datetime import date

import pytest

from app.data.loader import get_dataset
from app.services import proposals, replan
from app.services.substitutes import MAX_DAILY_SESSIONS, find_substitutes, module_base, teaches

DEMO_LECTURER = "MZD"  # docs/DEMO_SCRIPT.md


def test_module_base():
    assert module_base("CT044-3-1-IOOP-LAB-28") == "CT044-3-1-IOOP"
    assert module_base("MPU1132-BMK1(FS)-L-6 (Online)") == "MPU1132-BMK1(FS)"
    assert module_base("AAPP003-3-C-FVP-LAB-4") == "AAPP003-3-C-FVP"


def _all_sessions(days):
    ds = get_dataset()
    return [ds.sessions[i] for d in days for i in ds.by_date.get(d, [])]


def test_substitutes_are_free_and_teach_the_module():
    ds = get_dataset()
    checked = 0
    for s in _all_sessions([date(2026, 11, 13), date(2026, 11, 16), date(2026, 11, 17)])[:600]:
        for c in find_substitutes(s.id)["candidates"]:
            lid = c["lecturer_id"]
            assert lid != s.lecturer_id
            # genuinely teaches the module
            assert teaches(ds, lid, s) in ("section", "module")
            assert any(set(ds.sessions[i].module_ids) & set(s.module_ids)
                       or {module_base(m) for m in ds.sessions[i].module_ids} & {module_base(m) for m in s.module_ids}
                       or ds.sessions[i].module_name.lower() == s.module_name.lower()
                       for i in ds.by_lecturer[lid])
            # genuinely free
            assert ds.lect_busy.is_free(lid, s.date, s.start_min, s.end_min)
            # load cap
            assert len(ds.lect_busy.intervals(lid, s.date)) + 1 <= MAX_DAILY_SESSIONS
            checked += 1
    assert checked > 50


def test_ranking_prefers_same_section():
    ds = get_dataset()
    for s in _all_sessions([date(2026, 11, 16)]):
        c = find_substitutes(s.id)["candidates"]
        tiers = [x["match"] for x in c]
        assert tiers == sorted(tiers, key=lambda t: 0 if t == "section" else 1)


def test_demo_lecturer_gets_substitutes_and_reschedules():
    d = replan.create_disruption("LECTURER_UNAVAILABLE", {"lecturer_id": DEMO_LECTURER}, {"start": "2026-11-13", "end": "2026-11-13"}, "sick")
    p = replan.plan_replan(d["id"])
    types = [m["type"] for m in p["moves"]]
    assert types.count("SUBSTITUTE") >= 1 and types.count("RESCHEDULE") >= 1
    assert p["summary"]["clash_check"]["passed"]
    # a substitute is never double-booked across the proposal
    subs = [(m["substitute"], m["from"]["start"]) for m in p["moves"] if m["type"] == "SUBSTITUTE"]
    assert len(subs) == len(set(subs))


def test_decline_substitute_reschedules_instead():
    d = replan.create_disruption("LECTURER_UNAVAILABLE", {"lecturer_id": DEMO_LECTURER}, {"start": "2026-11-13", "end": "2026-11-13"})
    p = replan.plan_replan(d["id"])
    sub = next(m for m in p["moves"] if m["type"] == "SUBSTITUTE")
    p2 = replan.plan_replan(d["id"], {"decline_substitutes": [sub["session_id"]]})
    m2 = next(m for m in p2["moves"] if m["session_id"] == sub["session_id"])
    assert m2["type"] in ("RESCHEDULE", "ONLINE")


def test_execute_substitute_updates_lecturer_and_drafts(fresh_dataset, isolated_state):
    d = replan.create_disruption("LECTURER_UNAVAILABLE", {"lecturer_id": DEMO_LECTURER}, {"start": "2026-11-13", "end": "2026-11-13"})
    p = replan.plan_replan(d["id"])
    proposals.approve_proposal(p["id"], "Programme Leader")
    proposals.execute_proposal(p["id"])
    sub = next(m for m in p["moves"] if m["type"] == "SUBSTITUTE")
    s = fresh_dataset.sessions[sub["session_id"]]
    assert s.lecturer_id == sub["substitute"] and s.start_iso() == sub["from"]["start"] and s.room == sub["from"]["room"]
    emls = "".join(f.read_text() for f in (isolated_state / "outbox" / p["id"] / "drafts").glob("*.eml"))
    assert "Please confirm" in emls and f"lect-{sub['substitute'].lower()}@" in emls
