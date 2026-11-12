#!/usr/bin/env python3
"""Generate all mock / synthetic data (seeded, deterministic):

  data/rooms.json                 room catalogue with mock capacities (heuristics in app/data/catalog.py)
  data/group_sizes.json           students per (INTAKE, GROUPING), seeded 15-60
  data/synthetic/students.json    ~3,000 SYNTHETIC students across ~150 real intakes. Fields: id, name, intake, grouping,
                                  attendance_records = {"absent": [...]} generated against each group's REAL timetable,
                                  with profiles (steady / declining / sudden drop / at-risk) and crafted demo students.

No real person's data is used anywhere.
"""
from __future__ import annotations

import json
import random
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings  # noqa: E402
from app.data.catalog import build_room, group_size  # noqa: E402
from app.services.store import JsonStore, set_store  # noqa: E402

SEED = 20261112
N_INTAKES = 150
PER_INTAKE = 20

FIRST = ["Ari", "Bela", "Cato", "Dara", "Eko", "Fina", "Galen", "Hana", "Iko", "Jaya", "Kian", "Lio", "Mira", "Nadi", "Oren", "Pia",
         "Quin", "Rafi", "Sena", "Tavi", "Uma", "Vero", "Wira", "Xan", "Yara", "Zeno", "Amani", "Bayu", "Chidi", "Dewi", "Emre", "Farah",
         "Gita", "Hiro", "Imani", "Jun", "Kemi", "Lina", "Malik", "Nour", "Omar", "Priya", "Rina", "Sami", "Tariq", "Wei", "Yusuf", "Zara"]
LAST = ["Arden", "Bastian", "Corvo", "Delmar", "Everly", "Faron", "Galloway", "Harrow", "Ivers", "Jessup", "Kestrel", "Lomax",
        "Merrin", "Norcross", "Oakes", "Pellam", "Quarry", "Rowntree", "Selby", "Thorne", "Underhill", "Vance", "Wexley", "Yardley",
        "Zabel", "Anwar", "Binte", "Chowdhury", "Darmawan", "Effiong", "Farouk", "Gunawardena", "Haddad", "Iskandar", "Jumabek", "Kamau"]


def main() -> None:
    set_store(JsonStore(Path(tempfile.mkdtemp())))  # clean store: declared runtime holidays must not leak in
    from app.data.loader import get_dataset
    from app.services import attendance

    ds = get_dataset()
    rng = random.Random(SEED)
    now = settings.now()

    rooms = sorted({s.room for s in ds.sessions.values()} | {"ONLINE"})
    (ROOT / "data" / "rooms.json").write_text(json.dumps([build_room(r).to_dict() for r in rooms], indent=1))
    gs = {f"{i}|{g}": group_size(i, g) for (i, g) in sorted(ds.by_group)}
    (ROOT / "data" / "group_sizes.json").write_text(json.dumps(gs, separators=(",", ":")))
    print(f"rooms.json: {len(rooms)} rooms; group_sizes.json: {len(gs)} groups")

    eligible = [g for g in sorted(ds.by_group) if g[1] == "G1" and len(ds.by_group[g]) >= 6]
    rng.shuffle(eligible)
    chosen = sorted(eligible[:N_INTAKES])
    print(f"eligible intake groups: {len(eligible)}; chosen {len(chosen)}")

    def gen_absences(past: list[dict], profile: str, r: random.Random) -> list[str]:
        n, out = len(past), []
        target = {"steady": 0.05, "perfect": 0.0, "at_risk": r.uniform(0.16, 0.22)}.get(profile)
        for i, o in enumerate(past):
            if profile == "declining":
                p = 0.03 + 0.35 * i / max(1, n - 1)
            elif profile == "sudden_drop":
                p = 0.03 if (now.date() - o["date"]).days > 21 else 0.55
            else:
                p = target
            if r.random() < p:
                out.append(o["key"])
        return out

    students, sid = [], 0
    for g in chosen:
        past = [o for o in attendance.group_occurrences(g) if attendance.is_past(o, now)]
        for k in range(PER_INTAKE):
            r = random.Random(f"{SEED}:{g}:{k}")
            sid += 1
            profile = r.choices(["steady", "perfect", "declining", "sudden_drop", "at_risk"], [55, 5, 15, 10, 15])[0]
            students.append({"id": f"STU{sid:05d}", "name": f"{r.choice(FIRST)} {r.choice(LAST)}", "intake": g[0], "grouping": g[1],
                             "attendance_records": {"absent": gen_absences(past, profile, r)}})

    demo = build_demo_students(attendance, chosen, now)
    students = demo + students
    out = {"generated_at": now.isoformat(), "seed": SEED, "note": "SYNTHETIC students - not real people",
           "attendance_records_format": "absent = occurrence keys 'module|YYYY-MM-DD|start_min'; every other past session of the group's timetable is PRESENT",
           "students": students}
    p = ROOT / "data" / "synthetic"
    p.mkdir(parents=True, exist_ok=True)
    (p / "students.json").write_text(json.dumps(out, separators=(",", ":")))
    print(f"students.json: {len(students)} synthetic students, {len(demo)} demo")
    attendance.reload_students()
    for s in demo:
        f = attendance.attendance_forecast(s["id"])
        print(f"  {s['id']} {s['name']:<16} {f['current_percent']}%  remaining={f['remaining_sessions']} "
              f"max_more_absences={f['max_more_absences']} ({f['binding_module']})")


def build_demo_students(attendance, chosen, now):
    """Search absence patterns that give compelling, exact demo numbers (verified with the real forecast code)."""
    mma = attendance.max_more_absences
    thr = settings.attendance_threshold

    def info(g):
        occ = attendance.group_occurrences(g)
        past = [o for o in occ if attendance.is_past(o, now)]
        mods = defaultdict(lambda: [[], 0])
        for o in occ:
            if attendance.is_past(o, now):
                mods[o["module"]][0].append(o)
            else:
                mods[o["module"]][1] += 1
        return past, len(occ) - len(past), mods

    ranked = []
    for g in chosen:
        past, fut, mods = info(g)
        if 14 <= fut <= 40 and len(past) >= 25 and len(mods) >= 2:
            ranked.append((abs(fut - 22), g))
    groups = [g for _, g in sorted(ranked)] or chosen
    specs = [
        ("STU-DEMO-01", "Amani Kestrel", {"target": 0.83, "binding_mma": 2}),   # "can miss at most 2 more"
        ("STU-DEMO-02", "Bayu Darmawan", {"target": 0.87, "consec": 3}),         # sudden drop, 3 in a row
        ("STU-DEMO-03", "Farah Haddad", {"target": 0.76}),                       # already below threshold
        ("STU-DEMO-04", "Wei Lomax", {"target": 0.96}),                          # healthy contrast
        ("STU-DEMO-05", "Nour Effiong", {"unreachable": True}),                  # can't reach 80% in one module
    ]
    out = []
    for idx, (sid, name, sp) in enumerate(specs):
        g = groups[idx % len(groups)]
        past, _, mods = info(g)
        order = sorted(mods.items(), key=lambda kv: -len(kv[1][0]))
        absences: list[str] = []
        n_target = round(len(past) * (1 - sp.get("target", 0.8)))
        mname, (mpast, mrem) = order[0]
        if sp.get("binding_mma") is not None:
            for a in range(len(mpast) + 1):
                if mma(len(mpast) - a, len(mpast), mrem, thr) == sp["binding_mma"]:
                    absences += [o["key"] for o in mpast[len(mpast) - a:]]
                    break
            per_mod = defaultdict(int)
            for o in sorted((o for _, (mp, _) in order[1:] for o in mp), key=lambda o: o["date"]):
                if len(absences) >= n_target:
                    break
                mp, mr = mods[o["module"]]
                if mma(len(mp) - per_mod[o["module"]] - 1, len(mp), mr, thr) >= sp["binding_mma"]:
                    absences.append(o["key"])
                    per_mod[o["module"]] += 1
        elif sp.get("unreachable"):
            for a in range(len(mpast) + 1):
                if mma(len(mpast) - a, len(mpast), mrem, thr) < 0:
                    absences += [o["key"] for o in mpast[:a]]
                    break
        else:
            r = random.Random(sid)
            if sp.get("consec"):
                absences += [o["key"] for o in mpast[-sp["consec"]:]]
            pool = [o for o in past if o["key"] not in absences]
            absences += [o["key"] for o in r.sample(pool, min(max(0, n_target - len(absences)), len(pool)))]
        out.append({"id": sid, "name": name, "intake": g[0], "grouping": g[1], "attendance_records": {"absent": sorted(set(absences))}})
    return out


if __name__ == "__main__":
    main()
