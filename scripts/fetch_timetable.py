#!/usr/bin/env python3
"""Download the PUBLIC APU timetable + intake listing, pseudonymise, and write a dated snapshot.

    python scripts/fetch_timetable.py            # writes data/snapshots/timetable_<date>.json + LATEST
    python scripts/fetch_timetable.py --check    # fetch and print stats only

The raw (non-pseudonymised) payload is never written to disk.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.data.pseudonymise import assert_no_pii, pseudonymise_rows  # noqa: E402

TT_URL = "https://s3-ap-southeast-1.amazonaws.com/open-ws/weektimetable"
INTAKE_URL = "https://s3-ap-southeast-1.amazonaws.com/open-ws/intake_listing"
MYT = timezone(timedelta(hours=8))


def fetch_json(url: str, timeout: int = 30):
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "campus-time-ops/0.1 (hackathon prototype)"})
    r.raise_for_status()
    return r.json()  # requests transparently gunzips


def fetch_pseudonymised() -> tuple[list[dict], list[dict]]:
    raw = fetch_json(TT_URL)
    real_names = {r.get("NAME") for r in raw if r.get("NAME")}
    rows = pseudonymise_rows(raw)
    del raw
    assert_no_pii(rows, real_names)
    intakes = [
        {"INTAKE_CODE": i["INTAKE_CODE"].strip(), "COLOR": i.get("COLOR")}
        for i in fetch_json(INTAKE_URL)
        if i.get("INTAKE_CODE")
    ]
    return rows, intakes


def stats(rows: list[dict]) -> dict:
    phys = {(r["LECTID"], r["ROOM"], r["TIME_FROM_ISO"]) for r in rows}
    dates = sorted({r["DATESTAMP_ISO"] for r in rows})
    return {
        "rows": len(rows),
        "physical_sessions": len(phys),
        "intakes": len({r["INTAKE"] for r in rows}),
        "class_codes": len({r["CLASS_CODE"] for r in rows}),
        "lecturers": len({r["LECTID"] for r in rows}),
        "rooms": len({r["ROOM"] for r in rows}),
        "date_from": dates[0] if dates else None,
        "date_to": dates[-1] if dates else None,
        "rows_per_day": dict(sorted(Counter(r["DATESTAMP_ISO"] for r in rows).items())),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "data" / "snapshots"))
    args = ap.parse_args()

    rows, intakes = fetch_pseudonymised()
    st = stats(rows)
    print(json.dumps({k: v for k, v in st.items() if k != "rows_per_day"}, indent=2))
    if args.check:
        return
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    day = datetime.now(MYT).date().isoformat()
    payload = {
        "meta": {
            "source": TT_URL,
            "fetched_at": datetime.now(MYT).isoformat(timespec="seconds"),
            "pseudonymised": True,
            "stats": st,
        },
        "rows": rows,
    }
    (out / f"timetable_{day}.json").write_text(json.dumps(payload, separators=(",", ":")))
    (out / f"intakes_{day}.json").write_text(json.dumps(intakes, separators=(",", ":")))
    (out / "LATEST").write_text(day + "\n")
    print(f"wrote {out}/timetable_{day}.json ({len(rows)} rows) and LATEST")


if __name__ == "__main__":
    main()
