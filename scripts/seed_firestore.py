#!/usr/bin/env python3
"""Seed Firestore (or the emulator: export FIRESTORE_EMULATOR_HOST=localhost:8080) with a clean demo state and the
synthetic students (read-only reference collection `students`, attendance absences omitted for size)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("STORE_BACKEND", "firestore")

from app.services.store import FirestoreStore  # noqa: E402

st = FirestoreStore()
st.clear()
students = json.loads((ROOT / "data" / "synthetic" / "students.json").read_text())["students"]
batch = st.db.batch()
for i, s in enumerate(students, 1):
    doc = {k: v for k, v in s.items() if k != "absences"} | {"absence_count": len(s.get("absences", []))}
    batch.set(st.db.collection("students").document(s["id"]), doc)
    if i % 400 == 0:
        batch.commit()
        batch = st.db.batch()
batch.commit()
print(f"Firestore seeded: cleared state collections, wrote {len(students)} synthetic students")
