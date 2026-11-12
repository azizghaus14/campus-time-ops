"""Attendance Risk: forecast equals a hand calculation for 3 test students; risk list is ranked and read-only."""
import math
from collections import defaultdict

import pytest

from app.services import attendance
from app.services.attendance import max_more_absences
from app.services.store import get_store


@pytest.mark.parametrize(
    "attended,held,remaining,expected",
    [
        (20, 24, 6, 2),   # (26-k)/30 >= .8 -> k <= 2
        (8, 10, 5, 1),    # (13-k)/15 >= .8 -> k <= 1
        (10, 10, 10, 4),  # (20-k)/20 >= .8 -> k <= 4
        (6, 10, 2, -1),   # 8/12 = .667 < .8 even with full attendance
        (16, 20, 0, 0),   # exactly 80%, nothing left
    ],
)
def test_max_more_absences_hand_vectors(attended, held, remaining, expected):
    assert max_more_absences(attended, held, remaining, 0.80) == expected


def _hand(student_id: str):
    """Independent hand calculation from raw records + remaining sessions, per module, by brute force."""
    att = attendance.get_attendance(student_id)
    f = attendance.attendance_forecast(student_id)
    rem = {p["module"]: p["remaining"] for p in f["per_module"]}
    held, attended = defaultdict(int), defaultdict(int)
    for r in att["records"]:
        held[r["module"]] += 1
        attended[r["module"]] += r["status"] == "PRESENT"
    best = math.inf
    for m in set(held) | set(rem):
        n, a, r = held[m], attended[m], rem.get(m, 0)
        ok = [k for k in range(r + 1) if (a + r - k) >= 0.8 * (n + r) - 1e-9]
        best = min(best, max(ok) if ok else -1)
    return best, f


@pytest.mark.parametrize("sid", ["STU-DEMO-01", "STU-DEMO-02", "STU-DEMO-04"])
def test_forecast_matches_hand_calculation(sid):
    best, f = _hand(sid)
    assert f["max_more_absences"] == best
    assert f["remaining_sessions"] > 0
    assert f["held"] == sum(p["held"] for p in f["per_module"])


def test_demo_student_story():
    f = attendance.attendance_forecast("STU-DEMO-01")
    assert f["max_more_absences"] == 2
    assert "sessions left this term" in f["message"]
    assert f["remaining_in_published_timetable"] > 0  # real feed sessions are part of 'remaining'


def test_student_schema_is_minimal():
    rec = attendance.get_student_record("STU00001")
    assert set(rec) == {"id", "name", "intake", "grouping", "attendance_records"}


def test_risk_list_ranked_and_read_only():
    before = {c: len(get_store().list(c)) for c in ("proposals", "audit")}
    r = attendance.attendance_risk_list(limit=5000)
    assert r["at_risk"] > 0 and r["below_threshold"] > 0
    scores = [x["risk_score"] for x in r["students"]]
    assert scores == sorted(scores, reverse=True)
    assert any(x["student_id"] == "STU-DEMO-03" for x in r["students"])
    assert {c: len(get_store().list(c)) for c in ("proposals", "audit")} == before
