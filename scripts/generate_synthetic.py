#!/usr/bin/env python3
"""Generate all mock / synthetic data (seeded, deterministic):

  data/rooms.json                 room catalogue with mock capacities (heuristics in app/data/catalog.py)
  data/group_sizes.json           students per (INTAKE, GROUPING), seeded 15-60
  data/synthetic/students.json    ~3,000 SYNTHETIC students across ~150 real intakes, 30-40% international,
                                  attendance generated against each group's real timetable; >= 6 crafted demo students
  data/demo_passports/*.png       SPECIMEN passport images (fictional state 'UTO') with ICAO 9303 MRZ, 1 bad check digit

No real person's data is used anywhere.
"""
from __future__ import annotations

import json
import random
import sys
import tempfile
from collections import defaultdict
from datetime import date, timedelta
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
NATIONALITIES = [("Indonesia", "IDN"), ("China", "CHN"), ("Bangladesh", "BGD"), ("Nigeria", "NGA"), ("Pakistan", "PAK"), ("India", "IND"),
                 ("Sri Lanka", "LKA"), ("Yemen", "YEM"), ("Kazakhstan", "KAZ"), ("Sudan", "SDN"), ("Iran", "IRN"), ("Maldives", "MDV"),
                 ("Egypt", "EGY"), ("Kenya", "KEN"), ("Vietnam", "VNM")]


def main() -> None:
    # clean in-memory store so declared runtime holidays don't leak into generation
    set_store(JsonStore(Path(tempfile.mkdtemp())))
    from app.data.loader import get_dataset
    from app.services import visa

    ds = get_dataset()
    rng = random.Random(SEED)
    now = settings.now()

    # ---------------- rooms + group sizes
    rooms = sorted({s.room for s in ds.sessions.values()} | {"ONLINE"})
    (ROOT / "data" / "rooms.json").write_text(json.dumps([build_room(r).to_dict() for r in rooms], indent=1))
    gs = {f"{i}|{g}": group_size(i, g) for (i, g) in sorted(ds.by_group)}
    (ROOT / "data" / "group_sizes.json").write_text(json.dumps(gs, separators=(",", ":")))
    print(f"rooms.json: {len(rooms)} rooms; group_sizes.json: {len(gs)} groups")

    # ---------------- choose intakes with a meaningful timetable
    def remaining_and_past(g):
        occ = visa.group_occurrences(g)
        past = [o for o in occ if visa._is_past(o, now)]
        return len(past), len(occ) - len(past), occ

    eligible = []
    for g in sorted(ds.by_group):
        if g[1] != "G1":
            continue
        n_feed = len(ds.by_group[g])
        if n_feed >= 6:
            eligible.append(g)
    rng.shuffle(eligible)
    chosen = sorted(eligible[:N_INTAKES])
    print(f"eligible intake groups: {len(eligible)}; chosen {len(chosen)}")

    students = []
    sid = 0

    def make_identity(international: bool, r: random.Random):
        if international:
            nat, code = r.choice(NATIONALITIES)
        else:
            nat, code = "Malaysia", "MYS"
        name = f"{r.choice(FIRST)} {r.choice(LAST)}"
        dob = date(r.randint(1999, 2007), r.randint(1, 12), r.randint(1, 28)).isoformat()
        return name, nat, code, dob

    def gen_absences(occ_past: list[dict], profile: str, r: random.Random) -> list[str]:
        n = len(occ_past)
        out = []
        target = {"steady": 0.05, "perfect": 0.0, "at_risk": r.uniform(0.16, 0.22)}.get(profile)
        for i, o in enumerate(occ_past):
            frac = i / max(1, n - 1)
            if profile == "declining":
                p = 0.03 + 0.35 * frac
            elif profile == "sudden_drop":
                p = 0.03 if (now.date() - o["date"]).days > 21 else 0.55
            else:
                p = target
            if r.random() < p:
                out.append(o["key"])
        return out

    for g in chosen:
        n_past, n_rem, occ = remaining_and_past(g)
        past = [o for o in occ if visa._is_past(o, now)]
        lecturers = sorted({o["lecturer_id"] for o in occ})
        intl_share = rng.uniform(0.30, 0.40)
        for k in range(PER_INTAKE):
            r = random.Random(f"{SEED}:{g}:{k}")
            sid += 1
            intl = r.random() < intl_share
            name, nat, code, dob = make_identity(intl, r)
            profile = r.choices(["steady", "perfect", "declining", "sudden_drop", "at_risk"], [55, 5, 15, 10, 15])[0]
            pass_exp = (now.date() + timedelta(days=r.randint(30, 540))).isoformat() if intl else None
            pp_exp = (now.date() + timedelta(days=r.randint(400, 3000))).isoformat() if intl else None
            students.append({
                "id": f"STU{sid:05d}", "name": name, "intake": g[0], "grouping": g[1], "nationality": nat, "nationality_code": code,
                "is_international": intl, "pass_expiry": pass_exp, "passport_no": (f"X{r.randint(10000000, 99999999)}" if intl else None),
                "passport_expiry": pp_exp, "dob": dob, "sex": r.choice("MF"), "advisor_id": lecturers[k % len(lecturers)] if lecturers else None,
                "profile": profile, "absences": gen_absences(past, profile, r), "demo": False,
            })
    # two random international students whose passport expires before the pass
    intl = [s for s in students if s["is_international"] and s["pass_expiry"]]
    for s in random.Random(SEED + 1).sample(intl, 2):
        s["passport_expiry"] = (date.fromisoformat(s["pass_expiry"]) - timedelta(days=45)).isoformat()

    # ---------------- crafted demo students
    demo = build_demo_students(ds, visa, chosen, now)
    students = demo + students
    out = {"generated_at": now.isoformat(), "seed": SEED, "note": "SYNTHETIC students - not real people", "students": students}
    p = ROOT / "data" / "synthetic"
    p.mkdir(parents=True, exist_ok=True)
    (p / "students.json").write_text(json.dumps(out, separators=(",", ":")))
    print(f"students.json: {len(students)} students ({sum(s['is_international'] for s in students)} international), {len(demo)} demo")

    # verify demo numbers with the real forecast code
    settings_data = settings.data_dir
    visa.reload_students()
    for s in demo:
        f = visa.attendance_forecast(s["id"])
        print(f"  {s['id']} {s['name']:<18} {s['profile']:<12} {f['current_percent']}%  remaining={f['remaining_sessions']} "
              f"mma={f['max_more_absences']} ({f['binding_module']})")
    make_passports(demo)


def build_demo_students(ds, visa, chosen, now):
    """Search for absence patterns that produce compelling, exact demo numbers."""
    from app.services.visa import max_more_absences

    thr = settings.attendance_threshold
    # prefer groups with several modules and plenty remaining
    def info(g):
        occ = visa.group_occurrences(g)
        past = [o for o in occ if visa._is_past(o, now)]
        fut = [o for o in occ if not visa._is_past(o, now)]
        mods = defaultdict(lambda: [[], 0])
        for o in past:
            mods[o["module"]][0].append(o)
        for o in fut:
            mods[o["module"]][1] += 1
        return occ, past, fut, mods

    ranked = []
    for g in chosen:
        occ, past, fut, mods = info(g)
        if 14 <= len(fut) <= 40 and len(past) >= 25 and len(mods) >= 2:
            ranked.append((abs(len(fut) - 22), g))
    ranked.sort()
    groups = [g for _, g in ranked] or chosen

    specs = [
        ("STU-DEMO-01", "Amani Kestrel", "Kenya", "KEN", "at_risk", {"target": 0.83, "binding_mma": 2}),
        ("STU-DEMO-02", "Bayu Darmawan", "Indonesia", "IDN", "sudden_drop", {"target": 0.87, "consec": 3}),
        ("STU-DEMO-03", "Farah Haddad", "Egypt", "EGY", "at_risk", {"target": 0.76, "passport_before_pass": True}),
        ("STU-DEMO-04", "Wei Lomax", "China", "CHN", "steady", {"target": 0.96, "passport_soon": True}),
        ("STU-DEMO-05", "Tariq Chowdhury", "Bangladesh", "BGD", "declining", {"target": 0.88, "declining": True, "name_mismatch": True}),
        ("STU-DEMO-06", "Nour Effiong", "Nigeria", "NGA", "at_risk", {"target": 0.80, "unreachable": True}),
        ("STU-DEMO-07", "Rina Iskandar", "Malaysia", "MYS", "steady", {"target": 0.94, "local": True}),
    ]
    out = []
    for idx, (sid, name, nat, code, profile, sp) in enumerate(specs):
        g = groups[idx % len(groups)]
        occ, past, fut, mods = info(g)
        order = sorted(mods.items(), key=lambda kv: -len(kv[1][0]))
        absences: list[str] = []
        n_target_abs = round(len(past) * (1 - sp["target"]))
        if sp.get("binding_mma") is not None:
            mname, (mpast, mrem) = order[0]
            # choose absences a in binding module so that mma == wanted
            for a in range(len(mpast) + 1):
                if max_more_absences(len(mpast) - a, len(mpast), mrem, thr) == sp["binding_mma"]:
                    absences += [o["key"] for o in mpast[-a:]] if a else []
                    break
            rest = [o for m, (mp, _) in order[1:] for o in mp]
            need = max(0, n_target_abs - len(absences))
            # spread remaining absences thinly across other modules while keeping them non-binding
            per_mod = defaultdict(int)
            for o in sorted(rest, key=lambda o: o["date"]):
                if need <= 0:
                    break
                mp, mr = mods[o["module"]]
                if max_more_absences(len(mp) - per_mod[o["module"]] - 1, len(mp), mr, thr) >= sp["binding_mma"]:
                    absences.append(o["key"])
                    per_mod[o["module"]] += 1
                    need -= 1
        elif sp.get("unreachable"):
            mname, (mpast, mrem) = order[0]
            for a in range(len(mpast) + 1):
                if max_more_absences(len(mpast) - a, len(mpast), mrem, thr) < 0:
                    absences += [o["key"] for o in mpast[:a]]
                    break
        else:
            r = random.Random(sid)
            ordered = sorted(past, key=lambda o: (o["date"], o["start"]))
            if sp.get("consec"):
                mname, (mpast, _) = order[0]
                absences += [o["key"] for o in mpast[-sp["consec"]:]]
            pool = [o for o in ordered if o["key"] not in absences]
            if sp.get("declining"):
                w = [i + 1 for i in range(len(pool))]
                picks = set()
                while len(picks) < max(0, n_target_abs - len(absences)) and len(picks) < len(pool):
                    picks.add(r.choices(range(len(pool)), weights=w)[0])
                absences += [pool[i]["key"] for i in sorted(picks)]
            else:
                k = max(0, n_target_abs - len(absences))
                absences += [o["key"] for o in r.sample(pool, min(k, len(pool)))]
        local = sp.get("local")
        pass_exp = None if local else (now.date() + timedelta(days=120 + 37 * idx)).isoformat()
        pp_exp = None
        if not local:
            pp_exp = (now.date() + timedelta(days=1500)).isoformat()
            if sp.get("passport_before_pass"):
                pp_exp = (date.fromisoformat(pass_exp) - timedelta(days=40)).isoformat()
            if sp.get("passport_soon"):
                pp_exp = (now.date() + timedelta(days=150)).isoformat()
                pass_exp = (now.date() + timedelta(days=400)).isoformat()
        lects = sorted({o["lecturer_id"] for o in occ})
        out.append({
            "id": sid, "name": name, "intake": g[0], "grouping": g[1], "nationality": nat, "nationality_code": code,
            "is_international": not local, "pass_expiry": pass_exp, "passport_no": None if local else f"P{7300000 + idx * 1111:08d}"[:9],
            "passport_expiry": pp_exp, "dob": f"200{idx % 6}-0{(idx % 9) + 1}-1{idx % 9}", "sex": "FM"[idx % 2], "advisor_id": lects[0] if lects else None,
            "profile": profile, "absences": sorted(set(absences)), "demo": True,
            "demo_story": {"STU-DEMO-01": "Hero demo: 'how many more classes can I miss?'", "STU-DEMO-02": "Sudden drop: 3 consecutive absences -> advisor meeting",
                           "STU-DEMO-03": "Below 80% + passport expires before pass -> formal letter", "STU-DEMO-04": "Healthy attendance, passport expiring in ~5 months",
                           "STU-DEMO-05": "Declining trend; passport name differs from record", "STU-DEMO-06": "Cannot reach 80% in one module -> IO review",
                           "STU-DEMO-07": "Local student (not in Visa Guardian scope)"}[sid],
        })
    return out


def make_passports(demo: list[dict]) -> None:
    from PIL import Image, ImageDraw, ImageFont
    from PIL.PngImagePlugin import PngInfo

    from app.services.mrz import build_td3

    outdir = ROOT / "data" / "demo_passports"
    outdir.mkdir(parents=True, exist_ok=True)
    for f in outdir.glob("*.png"):
        f.unlink()
    by = {s["id"]: s for s in demo}
    cases = [
        ("specimen_01_valid_STU-DEMO-01.png", by["STU-DEMO-01"], {}, "valid"),
        ("specimen_03_expires_before_pass_STU-DEMO-03.png", by["STU-DEMO-03"], {}, "valid MRZ; passport expires before pass"),
        ("specimen_04_valid_expiring_STU-DEMO-04.png", by["STU-DEMO-04"], {}, "valid MRZ; passport expires within 6 months"),
        ("specimen_05_name_mismatch_STU-DEMO-05.png", by["STU-DEMO-05"], {"given": "TAREK"}, "valid MRZ; name differs from record"),
        ("specimen_02_bad_check_digit_STU-DEMO-02.png", by["STU-DEMO-02"], {"tamper": True}, "INVALID: wrong document-number check digit"),
    ]
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 22)
        big = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 26)
    except Exception:
        font = big = ImageFont.load_default()
    manifest = []
    for fname, s, mod, desc in cases:
        given, surname = s["name"].split()[0], s["name"].split()[-1]
        given = mod.get("given", given)
        l1, l2 = build_td3("P", "UTO", surname, given, s["passport_no"], "UTO", s["dob"], s["sex"], s["passport_expiry"])
        if mod.get("tamper"):
            wrong = str((int(l2[9]) + 3) % 10)
            l2 = l2[:9] + wrong + l2[10:]
        im = Image.new("RGB", (1000, 640), (236, 241, 236))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 1000, 70], fill=(40, 70, 110))
        d.text((30, 20), "UTOPIA  -  PASSPORT  (SPECIMEN, FICTIONAL)", fill="white", font=big)
        d.rectangle([40, 110, 260, 380], outline=(90, 90, 90), width=3)
        d.text((95, 230), "PHOTO", fill=(120, 120, 120), font=big)
        rows = [("Type", "P"), ("Issuing state", "UTO (fictional)"), ("Surname", surname.upper()), ("Given names", given.upper()),
                ("Passport No.", s["passport_no"]), ("Date of birth", s["dob"]), ("Sex", s["sex"]), ("Date of expiry", s["passport_expiry"])]
        for i, (k, v) in enumerate(rows):
            d.text((300, 110 + i * 34), f"{k}:", fill=(80, 80, 80), font=font)
            d.text((540, 110 + i * 34), v, fill=(10, 10, 10), font=font)
        d.rectangle([0, 470, 1000, 640], fill=(250, 250, 250))
        d.text((20, 505), l1, fill="black", font=font)
        d.text((20, 555), l2, fill="black", font=font)
        wm = Image.new("RGBA", im.size, (0, 0, 0, 0))
        wd = ImageDraw.Draw(wm)
        try:
            wf = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 120)
        except Exception:
            wf = big
        wd.text((150, 230), "SPECIMEN", fill=(200, 30, 30, 90), font=wf)
        im = Image.alpha_composite(im.convert("RGBA"), wm.rotate(18, center=(500, 320))).convert("RGB")
        meta = PngInfo()
        meta.add_text("mrz", f"{l1}\n{l2}")
        meta.add_text("note", "SPECIMEN - fictional data generated by Campus Time Ops")
        im.save(outdir / fname, pnginfo=meta)
        manifest.append({"file": fname, "student_id": s["id"], "expect": desc, "mrz": [l1, l2]})
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"demo_passports: {len(manifest)} specimen images")


if __name__ == "__main__":
    main()
