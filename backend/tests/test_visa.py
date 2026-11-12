"""M8: Visa Guardian forecast equals a hand calculation; MRZ validator (ICAO 9303)."""
import json
import math
from collections import defaultdict

import pytest

from app.config import settings
from app.services import mrz, visa
from app.services.visa import max_more_absences


@pytest.mark.parametrize(
    "attended,held,remaining,expected",
    [
        (20, 24, 6, 2),   # (26-k)/30 >= .8 -> k <= 2
        (8, 10, 5, 1),    # (13-k)/15 >= .8 -> k <= 1
        (10, 10, 10, 4),  # (20-k)/20 >= .8 -> k <= 4
        (6, 10, 2, -1),   # (8)/12 = .667 < .8 even with full attendance
        (16, 20, 0, 0),   # exactly 80%, nothing left
    ],
)
def test_max_more_absences_hand_vectors(attended, held, remaining, expected):
    assert max_more_absences(attended, held, remaining, 0.80) == expected


def _hand(student_id: str):
    """Independent hand calculation from the raw records + remaining sessions, per module, brute force."""
    att = visa.get_attendance(student_id)
    f = visa.attendance_forecast(student_id)
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


@pytest.mark.parametrize("sid", ["STU-DEMO-01", "STU-DEMO-02", "STU-DEMO-05"])
def test_forecast_matches_hand_calculation(sid):
    best, f = _hand(sid)
    assert f["max_more_absences"] == best
    assert f["remaining_sessions"] > 0
    assert f["held"] == sum(p["held"] for p in f["per_module"])


def test_demo_student_story():
    f = visa.attendance_forecast("STU-DEMO-01")
    assert f["max_more_absences"] == 2
    assert "sessions left this term" in f["message"]
    assert f["remaining_in_published_timetable"] > 0  # real feed sessions are part of 'remaining'


def test_risk_sweep_ranks_and_proposes_steps():
    sw = visa.visa_risk_sweep(limit=50)
    assert sw["at_risk"] > 0
    scores = [r["risk_score"] for r in sw["students"]]
    assert scores == sorted(scores, reverse=True)
    assert all(r["proposed_step"] in visa.LADDER for r in sw["students"])
    demo3 = next(r for r in sw["students"] if r["student_id"] == "STU-DEMO-03")
    assert demo3["proposed_step"] == "R-ESC-3"


# ----------------------------------------------------------------- MRZ
ICAO_L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
ICAO_L2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"


def test_icao_reference_example_valid():
    p = mrz.parse_td3(ICAO_L1, ICAO_L2)
    assert p["valid"], p["check_digits"]
    assert p["surname"] == "ERIKSSON" and p["given_names"] == "ANNA MARIA" and p["document_number"] == "L898902C3"


def test_icao_reference_tampered_rejected():
    bad = ICAO_L2[:9] + "5" + ICAO_L2[10:]
    p = mrz.parse_td3(ICAO_L1, bad)
    assert not p["valid"] and not p["check_digits"]["document_number"]


def test_build_td3_roundtrip():
    l1, l2 = mrz.build_td3("P", "UTO", "Lomax", "Wei", "P7303333", "UTO", "2003-04-13", "M", "2031-01-01")
    p = mrz.parse_td3(l1, l2)
    assert p["valid"] and p["expiry_date"] == "2031-01-01" and p["date_of_birth"] == "2003-04-13"


def test_specimen_images_accept_valid_reject_bad():
    man = json.loads((settings.data_dir / "demo_passports" / "manifest.json").read_text())
    for item in man:
        raw = (settings.data_dir / "demo_passports" / item["file"]).read_bytes()
        res = mrz.parse_passport_image(image_bytes=raw, student_id=item["student_id"])
        codes = {f["code"] for f in res["flags"]}
        if "bad_check_digit" in item["file"]:
            assert not res["valid"] and "CHECK_DIGIT_FAILED" in codes
        else:
            assert res["valid"], item["file"]
        if "expires_before_pass" in item["file"]:
            assert "PASSPORT_EXPIRES_BEFORE_PASS" in codes
        if "name_mismatch" in item["file"]:
            assert "NAME_MISMATCH" in codes
        if item["file"].startswith("specimen_01"):
            assert res["ok"], res["flags"]
