"""M1: snapshot integrity, physical-session grouping (§4.1), privacy (§4.4)."""
import json
from collections import Counter

from app.config import settings
from app.data.catalog import classify_room
from app.data.pseudonymise import pseudonym_for, pseudonymise_row


def _snapshot():
    snap = settings.data_dir / "snapshots"
    latest = (snap / "LATEST").read_text().strip()
    return json.loads((snap / f"timetable_{latest}.json").read_text())


def test_row_counts_match_snapshot_meta(ds):
    payload = _snapshot()
    st = payload["meta"]["stats"]
    assert len(ds.rows) == st["rows"]
    assert len({r["INTAKE"] for r in ds.rows}) == st["intakes"]
    assert len({r["LECTID"] for r in ds.rows}) == st["lecturers"]
    # §4.1 ballpark for a recent pull
    assert 15_000 <= len(ds.rows) <= 40_000


def test_physical_session_grouping(ds):
    keys = {(r["LECTID"], r["ROOM"], r["TIME_FROM_ISO"]) for r in ds.rows}
    assert len(ds.sessions) == len(keys)
    # every row is represented exactly once as a group inside its physical session
    assert sum(len(s.groups) for s in ds.sessions.values()) == len({(r["LECTID"], r["ROOM"], r["TIME_FROM_ISO"], r["INTAKE"], r["GROUPING"]) for r in ds.rows})
    biggest = max(len(s.groups) for s in ds.sessions.values())
    assert 50 <= biggest <= 200  # combined lectures (~123 intakes)


def test_weekday_volume(ds):
    per_day = Counter(s.date.weekday() for s in ds.sessions.values())
    weekday_days = Counter(s.date for s in ds.sessions.values() if s.date.weekday() < 5)
    busy = [n for d, n in weekday_days.items() if n > 100]
    assert busy and all(250 <= n <= 800 for n in busy)
    assert per_day[5] + per_day[6] < 0.02 * len(ds.sessions)


def test_no_pii_in_snapshot():
    payload = _snapshot()
    for r in payload["rows"]:
        assert "SAMACCOUNTNAME" not in r
        assert r["NAME"] == pseudonym_for(r["LECTID"])
    assert payload["meta"]["pseudonymised"] is True


def test_pseudonymise_row():
    r = pseudonymise_row({"LECTID": "ABC", "NAME": "Real Person", "SAMACCOUNTNAME": "real.person", "ROOM": "Tech Lab 6-16 (iMac Suite)�"})
    assert "SAMACCOUNTNAME" not in r and "Real" not in r["NAME"] and r["ROOM"] == "Tech Lab 6-16 (iMac Suite)"


def test_room_names_clean_and_classified(ds):
    for name in ds.rooms:
        assert name.isprintable() and "�" not in name
    assert classify_room("Auditorium 3 @ Block C Level 9")[0] == "auditorium"
    assert classify_room("Tech Lab 4-01")[0] == "lab"
    assert classify_room("B-01-GEOLOGY LAB")[0] == "specialist_lab"
    assert classify_room("D-07-13")[0] == "classroom"
    assert classify_room("ONLMCO3-13")[0] == "online"


def test_mock_room_capacities_stable(ds):
    from app.data.catalog import build_room

    for name, r in ds.rooms.items():
        assert build_room(name).capacity == r.capacity


def test_holidays_and_shuttle_loaded(ds):
    from datetime import date

    from app.services.shuttle import last_shuttle_min

    assert date(2026, 11, 9) in ds.holidays  # Deepavali in lieu
    assert date(2026, 12, 25) in ds.holidays
    assert last_shuttle_min(date(2026, 11, 17)) == 19 * 60 + 15  # Tue, LRT last regular
    assert last_shuttle_min(date(2026, 11, 21)) is None  # Saturday: no service listed
