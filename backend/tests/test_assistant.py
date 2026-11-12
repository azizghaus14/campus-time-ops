"""In-app assistant + role permissions + campus model."""
from datetime import date

import pytest

from app.services import campus
from app.services.assistant import handle, parse_dates
from app.services.errors import Forbidden
from app.services.identity import Identity, can_create_disruption

L, A, S = Identity("lecturer", "MZD"), Identity("admin"), Identity("student", "STU-DEMO-01")


@pytest.mark.parametrize("text,expected", [
    ("I'm sick tomorrow", (date(2026, 11, 13), date(2026, 11, 13))),
    ("Room is flooded until Friday", (date(2026, 11, 12), date(2026, 11, 13))),
    ("Monday 16 Nov is now a public holiday", (date(2026, 11, 16), date(2026, 11, 16))),
    ("next week", (date(2026, 11, 16), date(2026, 11, 20))),
    ("from 16 Nov to 18 Nov", (date(2026, 11, 16), date(2026, 11, 18))),
])
def test_parse_dates(text, expected):
    assert parse_dates(text) == expected


def test_lecturer_sick_flow_plans_then_needs_explicit_approval(fresh_dataset):
    r = handle("I'm sick tomorrow, sort out my classes", L)
    types = [c["type"] for c in r["cards"]]
    assert types == ["impact", "proposal"] and r["cards"][1]["status"] == "DRAFT" and r["cards"][1]["can_approve"]
    assert "Nothing has changed yet" in r["reply"]
    r2 = handle("move it to the afternoon", L, r["context"])
    assert r2["cards"][0]["version"] == 2
    r3 = handle("approve", L, r2["context"])
    assert r3["cards"][0]["type"] == "executed" and r3["cards"][0]["actions"]["calendar_events"] == 3


def test_roles_are_enforced():
    assert handle("Room B-04-03 is flooded until Friday", L)["cards"][0]["code"] == "ROLE_FORBIDDEN"
    assert handle("Monday 16 Nov is a public holiday", S)["cards"][0]["code"] == "ROLE_FORBIDDEN"
    assert handle("how many classes can STU-DEMO-02 miss", S)["cards"][0]["code"] == "ROLE_FORBIDDEN"
    with pytest.raises(Forbidden):
        can_create_disruption(L, "LECTURER_UNAVAILABLE", {"lecturer_id": "SPG"})  # someone else


def test_student_cannot_approve_lecturer_plan():
    r = handle("I'm sick tomorrow", L)
    out = handle("approve", S, r["context"])
    assert out["cards"][0]["code"] == "ROLE_FORBIDDEN"


def test_student_attendance_answer():
    r = handle("How many more classes can I miss?", S)
    assert r["cards"][0]["type"] == "attendance" and r["cards"][0]["max_more_absences"] == 2


def test_admin_slots_and_free_rooms():
    r = handle("find a 2 hour slot next week for AFCF2509BA and AFCF2609BA in an auditorium", A)
    assert r["cards"][0]["type"] == "slots" and r["cards"][0]["options"]
    r = handle("Which labs are free at 2pm tomorrow?", A)
    assert r["cards"][0]["type"] == "rooms" and r["cards"][0]["count"] > 0


def test_campus_layout_covers_all_physical_rooms(ds):
    lay = campus.layout()
    names = {r["name"] for b in lay["buildings"] for f in b["floors"] for r in f["rooms"]}
    physical = {n for n, r in ds.rooms.items() if not r.online}
    assert names == physical
    d = campus.day("2026-11-16")
    assert d["totals"]["sessions"] > 300 and set(d["rooms"]) == physical
