"""Replan: disruption -> affected sessions -> CP-SAT proposal (DRAFT) with rationale + citations."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Optional

from ..config import MYT, settings
from ..data.loader import Dataset, get_dataset
from ..domain import Disruption, DisruptionType, ProposalKind, ProposalStatus, hhmm, iso, parse_iso
from ..solver.decompose import solve_with_decomposition
from ..solver.model import Cand, SolveRequest, check_no_clashes, fmt_slot
from .audit import log_event
from .errors import Conflict, NotFound, ToolError, require
from .holidays import holiday_on, working_days
from .policy import cite
from .shuttle import latest_end_for_physical
from .store import get_store
from .timetable import parse_date, sdict

BULK_THRESHOLD = 40


# ------------------------------------------------------------------ disruptions
def _parse_window(window: Any, default_date: Optional[date] = None) -> tuple[datetime, datetime]:
    if not window and default_date:
        window = {"start": default_date.isoformat(), "end": default_date.isoformat()}
    require(isinstance(window, dict) and window.get("start"), "BAD_WINDOW", "window must be {start, end} (ISO date or datetime)")
    s_raw, e_raw = str(window["start"]), str(window.get("end") or window["start"])
    s = parse_iso(s_raw) if "T" in s_raw else datetime.fromisoformat(s_raw[:10]).replace(tzinfo=MYT)
    e = parse_iso(e_raw) if "T" in e_raw else datetime.fromisoformat(e_raw[:10]).replace(tzinfo=MYT) + timedelta(days=1)
    require(s < e, "BAD_WINDOW", "window start must be before end")
    require((e - s).days <= 31, "WINDOW_TOO_LONG", "max disruption window is 31 days")
    return s, e


def _affected(ds: Dataset, dtype: DisruptionType, scope: dict, ws: datetime, we: datetime) -> list[str]:
    now = settings.now()
    out = []
    if dtype == DisruptionType.LECTURER_UNAVAILABLE:
        ids = ds.by_lecturer.get(scope["lecturer_id"], [])
    elif dtype == DisruptionType.ROOM_UNAVAILABLE:
        ids = [i for r in scope["rooms"] for i in ds.by_room.get(r, [])]
    else:
        ids = [i for i in ds.sessions]
    for i in ids:
        s = ds.sessions[i]
        st = datetime(s.date.year, s.date.month, s.date.day, s.start_min // 60, s.start_min % 60, tzinfo=MYT)
        en = datetime(s.date.year, s.date.month, s.date.day, s.end_min // 60, s.end_min % 60, tzinfo=MYT)
        if st < we and en > ws and st >= now:
            out.append(i)
    return sorted(set(out), key=lambda i: (ds.sessions[i].date, ds.sessions[i].start_min, i))


def _impact(ds: Dataset, ids: list[str]) -> dict:
    groups = {g for i in ids for g in ds.sessions[i].groups}
    by_school = Counter(ds.sessions[i].school for i in ids)
    by_day = Counter(ds.sessions[i].date.isoformat() for i in ids)
    return {
        "sessions": len(ids),
        "intake_groups": len(groups),
        "intakes": len({g[0] for g in groups}),
        "students": sum(ds.group_sizes.get(g, 0) for g in groups),
        "lecturers": len({ds.sessions[i].lecturer_id for i in ids}),
        "online_sessions": sum(1 for i in ids if ds.rooms[ds.sessions[i].room].online),
        "by_school": dict(by_school.most_common()),
        "by_day": dict(sorted(by_day.items())),
    }


def create_disruption(type: str, scope: dict, window: Optional[dict] = None, reason: str = "", created_by: str = "agent") -> dict:
    ds = get_dataset()
    try:
        dtype = DisruptionType(str(type).upper())
    except ValueError:
        raise ToolError("BAD_TYPE", "type must be LECTURER_UNAVAILABLE | ROOM_UNAVAILABLE | HOLIDAY", got=type)
    scope = dict(scope or {})
    default_date = None
    if dtype == DisruptionType.LECTURER_UNAVAILABLE:
        lid = str(scope.get("lecturer_id", "")).upper().strip()
        require(lid, "MISSING_SCOPE", "scope.lecturer_id is required")
        if lid not in ds.by_lecturer:
            from .timetable import _lect_suggest

            raise NotFound("UNKNOWN_LECTURER", f"No lecturer '{lid}'", suggestions=_lect_suggest(ds, lid))
        scope = {"lecturer_id": lid, "lecturer_name": ds.lecturer_names[lid]}
    elif dtype == DisruptionType.ROOM_UNAVAILABLE:
        rooms = scope.get("rooms") or ([scope["room"]] if scope.get("room") else [])
        require(rooms, "MISSING_SCOPE", "scope.rooms is required")
        bad = [r for r in rooms if r not in ds.rooms]
        if bad:
            import difflib

            raise NotFound("UNKNOWN_ROOM", f"Unknown room(s): {bad}",
                           suggestions={b: difflib.get_close_matches(b, list(ds.rooms), n=3) for b in bad})
        scope = {"rooms": rooms}
    else:
        require(scope.get("date") or (window and window.get("start")), "MISSING_SCOPE", "scope.date is required for HOLIDAY")
        default_date = parse_date(scope.get("date") or window["start"])
        scope = {"date": default_date.isoformat(), "name": scope.get("name") or reason or "Declared public holiday"}
        window = {"start": default_date.isoformat(), "end": default_date.isoformat()}
    if dtype == DisruptionType.ROOM_UNAVAILABLE and not window:
        window = {"start": settings.now().isoformat(), "end": (settings.now() + timedelta(days=1)).date().isoformat()}
    ws, we = _parse_window(window, default_date)
    ids = _affected(ds, dtype, scope, ws, we)
    st = get_store()
    did = st.next_id("DIS")
    dis = Disruption(
        id=did, type=dtype, scope=scope, window={"start": ws.isoformat(), "end": we.isoformat()},
        reason=reason or "", created_by=created_by or "agent", created_at=settings.now().isoformat(),
        affected_session_ids=ids, impact=_impact(ds, ids),
    )
    d = dis.to_dict()
    d["status"] = "OPEN"
    st.put("disruptions", did, d)
    log_event(created_by, f"disruption.created {dtype.value}", None, after={"id": did, "scope": scope, "impact": d["impact"]})
    return _disruption_view(ds, d)


def _disruption_view(ds: Dataset, d: dict, with_sessions: bool = True, limit: int = 60) -> dict:
    out = {k: v for k, v in d.items() if k != "affected_session_ids"}
    imp = d["impact"]
    out["headline"] = (
        f"This affects {imp['sessions']} session{'s' if imp['sessions'] != 1 else ''}, "
        f"{imp['intake_groups']} intake group{'s' if imp['intake_groups'] != 1 else ''} and ~{imp['students']} students."
    )
    if with_sessions:
        ids = d["affected_session_ids"]
        out["affected_sessions"] = [sdict(ds, ds.sessions[i]) for i in ids[:limit] if i in ds.sessions]
        out["affected_truncated"] = len(ids) > limit
        out["affected_session_ids"] = ids
    return out


def get_disruption(disruption_id: str, with_sessions: bool = True, limit: int = 60) -> dict:
    d = get_store().get("disruptions", disruption_id)
    if not d:
        raise NotFound("UNKNOWN_DISRUPTION", f"No disruption {disruption_id}")
    return _disruption_view(get_dataset(), d, with_sessions, limit)


def list_disruptions() -> list[dict]:
    ds = get_dataset()
    items = get_store().list("disruptions")
    items.sort(key=lambda d: d["id"], reverse=True)
    return [_disruption_view(ds, d, with_sessions=False) for d in items]


# ------------------------------------------------------------------ planning
def _start_of(x: str) -> int:
    h, m = x.split(":")
    return int(h) * 60 + int(m)


def plan_replan(disruption_id: str, options: Optional[dict] = None, created_by: str = "agent") -> dict:
    ds = get_dataset()
    st = get_store()
    dis = st.get("disruptions", disruption_id)
    if not dis:
        raise NotFound("UNKNOWN_DISRUPTION", f"No disruption {disruption_id}")
    require(dis.get("status") != "EXECUTED", "ALREADY_EXECUTED", "This disruption has already been executed")
    o = dict(options or {})
    dtype = DisruptionType(dis["type"])
    sessions = [ds.sessions[i] for i in dis["affected_session_ids"] if i in ds.sessions]
    require(sessions, "NOTHING_TO_PLAN", "No upcoming sessions are affected by this disruption")

    now = settings.now()
    horizon = int(o.get("horizon_days", 10))
    require(1 <= horizon <= 30, "BAD_OPTION", "horizon_days must be 1..30")
    allow_sat = bool(o.get("allow_saturday", False))
    ws, we = parse_iso(dis["window"]["start"]), parse_iso(dis["window"]["end"])
    first_day = max(now.date(), ws.date())
    if dtype == DisruptionType.HOLIDAY:
        first_day = ws.date() + timedelta(days=1)
    coverage_end = ds.dates[-1]
    days = working_days(first_day, horizon, allow_saturday=allow_sat, last=coverage_end)
    if dtype == DisruptionType.HOLIDAY:
        days = [d for d in days if d != ws.date()]

    blocked_l: dict[str, list] = {}
    blocked_r: dict[str, list] = {}

    def _ivs(a: datetime, b: datetime):
        out, d = [], a.date()
        while d <= (b - timedelta(seconds=1)).date():
            s = a.hour * 60 + a.minute if d == a.date() else 0
            e = b.hour * 60 + b.minute if d == b.date() else 24 * 60
            out.append((d, s, e if e > 0 else 24 * 60))
            d += timedelta(days=1)
        return out

    if dtype == DisruptionType.LECTURER_UNAVAILABLE:
        blocked_l[dis["scope"]["lecturer_id"]] = _ivs(ws, we)
    elif dtype == DisruptionType.ROOM_UNAVAILABLE:
        for r in dis["scope"]["rooms"]:
            blocked_r[r] = _ivs(ws, we)

    preferred = None
    if o.get("preferred_slots"):
        preferred = [_start_of(x) for x in o["preferred_slots"] if ":" in str(x)] or None
    pins = {}
    for sid, p in (o.get("pins") or {}).items():
        p = dict(p)
        if isinstance(p.get("start"), str):
            p["start"] = _start_of(p["start"])
        pins[sid] = p
    substitutes = {}
    if o.get("substitute_lecturer"):
        sub = str(o["substitute_lecturer"]).upper()
        require(sub in ds.by_lecturer, "UNKNOWN_LECTURER", f"No substitute lecturer '{sub}'")
        substitutes["*"] = sub

    bulk = len(sessions) > BULK_THRESHOLD
    seed = int(o.get("seed", 42))
    req = SolveRequest(
        sessions=sessions,
        days=days,
        earliest=now + timedelta(hours=settings.notice_hours),
        blocked_lecturers=blocked_l,
        blocked_rooms=blocked_r,
        allow_online=bool(o.get("allow_online", True)),
        allow_same_slot=dtype == DisruptionType.ROOM_UNAVAILABLE or bool(substitutes),
        pins=pins,
        substitutes=substitutes,
        preferred_starts=preferred,
        max_moves_per_group_per_week=o.get("max_moves_per_group_per_week"),
        time_limit=float(o.get("time_limit", 10.0 if bulk else 3.0)),
        seed=seed,
        max_time_cands=12 if bulk else 40,
        max_room_cands=4 if bulk else 10,
        online_time_cands=2 if bulk else 4,
        workers=8 if bulk else 1,
    )
    res = solve_with_decomposition(req, ds, force_split=bool(o.get("force_decomposition")))
    clashes = check_no_clashes(ds, res.assignments, substitutes)

    moves = [_move_dict(ds, ds.sessions[sid], c, res.eliminations.get(sid, {}), dtype, substitutes) for sid, c in res.assignments.items()]
    moves.sort(key=lambda m: (m["from"]["start"], m["session_id"]))
    unresolved = []
    for sid, info in res.unresolved.items():
        s = ds.sessions[sid]
        unresolved.append({"session": sdict(ds, s), **info, "rule_ids": ["R-UNRESOLVED"]})

    n = len(sessions)
    n_online = sum(1 for m in moves if m["to"]["online"])
    n_room_only = sum(1 for m in moves if m["change"] == "room-only")
    summary = {
        "sessions": n,
        "placed_physical": len(moves) - n_online,
        "placed_online": n_online,
        "unresolved": len(unresolved),
        "room_only_changes": n_room_only,
        "share_physical": round((len(moves) - n_online) / n, 3),
        "share_online": round(n_online / n, 3),
        "share_unresolved": round(len(unresolved) / n, 3),
        "students_affected": dis["impact"]["students"],
        "intake_groups": dis["impact"]["intake_groups"],
        "clash_check": {"passed": not clashes, "problems": clashes[:20]},
        "candidate_days": [d.isoformat() for d in days],
        "notice_earliest": req.earliest.isoformat(),
    }
    if bulk:
        summary["by_school"] = _group_summary(moves, unresolved, key="school")
        summary["by_new_day"] = dict(sorted(Counter(m["to"]["date"] for m in moves).items()))
    rule_ids = sorted({r for m in moves for r in m["rule_ids"]} | ({"R-UNRESOLVED"} if unresolved else set()) | {"R-HITL", "R-NOTICE-HB"})
    if dtype == DisruptionType.HOLIDAY:
        rule_ids = sorted(set(rule_ids) | {"R-HOL"})

    # supersede older drafts for this disruption
    version = 1
    for p in st.list("proposals", disruption_id=disruption_id):
        version = max(version, p.get("version", 1) + 1)
        if p["status"] == ProposalStatus.DRAFT.value:
            p["status"] = ProposalStatus.SUPERSEDED.value
            st.put("proposals", p["id"], p)
    pid = st.next_id("PRO")
    prop = {
        "id": pid,
        "kind": ProposalKind.REPLAN.value,
        "disruption_id": disruption_id,
        "disruption_type": dtype.value,
        "title": _title(dis),
        "version": version,
        "status": ProposalStatus.DRAFT.value,
        "created_at": now.isoformat(),
        "created_by": created_by,
        "options": o,
        "moves": moves,
        "unresolved": unresolved,
        "score": res.stats.get("objective"),
        "stats": res.stats,
        "summary": summary,
        "citations": cite(rule_ids),
        "substitutes": substitutes,
        "bulk": bulk,
    }
    if clashes:
        prop["status"] = "INVALID"
    st.put("proposals", pid, prop)
    dis["status"] = "PLANNED"
    dis["latest_proposal_id"] = pid
    st.put("disruptions", disruption_id, dis)
    log_event(created_by, "proposal.drafted", pid, after={"moves": len(moves), "unresolved": len(unresolved), "solve_s": res.stats.get("total_s")})
    return proposal_view(prop)


def _title(dis: dict) -> str:
    sc = dis["scope"]
    if dis["type"] == "LECTURER_UNAVAILABLE":
        return f"{sc['lecturer_name']} ({sc['lecturer_id']}) unavailable"
    if dis["type"] == "ROOM_UNAVAILABLE":
        return f"Room{'s' if len(sc['rooms']) > 1 else ''} {', '.join(sc['rooms'])} unavailable"
    return f"Holiday declared: {date.fromisoformat(sc['date']).strftime('%a %d %b %Y')}"


def _group_summary(moves: list[dict], unresolved: list[dict], key: str) -> list[dict]:
    agg: dict[str, Counter] = defaultdict(Counter)
    for m in moves:
        agg[m[key]]["sessions"] += 1
        agg[m[key]]["online" if m["to"]["online"] else "physical"] += 1
        agg[m[key]]["students"] += m["students"]
    for u in unresolved:
        agg[u["session"][key]]["sessions"] += 1
        agg[u["session"][key]]["unresolved"] += 1
    rows = [{key: k, **{f: int(v.get(f, 0)) for f in ("sessions", "physical", "online", "unresolved", "students")}} for k, v in agg.items()]
    rows.sort(key=lambda r: -r["sessions"])
    return rows


def _move_dict(ds: Dataset, s, c: Cand, elim: dict, dtype: DisruptionType, substitutes: dict) -> dict:
    room = ds.rooms.get(c.room)
    same_time = c.day == s.date and c.start == s.start_min
    rule_ids = ["R-CLASH-GROUP", "R-CLASH-LECT", "R-DURATION"]
    parts = []
    lect = substitutes.get(s.id) or substitutes.get("*") or s.lecturer_id
    headcount = ds.session_students(s)
    if same_time:
        parts.append(f"Same time, room change only (no notice needed, R-NOTICE exception)")
        rule_ids.append("R-NOTICE")
    else:
        earlier = []
        for dstr, reasons in sorted(elim.get("by_day", {}).items()):
            if dstr < c.day.isoformat() and reasons:
                top = max(reasons.items(), key=lambda kv: kv[1])[0]
                earlier.append(f"{date.fromisoformat(dstr).strftime('%a %d')}: {top}")
        if earlier:
            parts.append("Earlier days ruled out - " + "; ".join(earlier[:3]))
        else:
            parts.append("Earliest suitable working day")
        rule_ids += ["R-NOTICE"]
        parts.append(f"lecturer {lect} and all {len(s.groups)} group(s) free")
    if c.room == "ONLINE" and not ds.rooms[s.room].online:
        parts.append("no physical room satisfied all hard rules -> online fallback (needs approver OK)")
        rule_ids.append("R-ONLINE")
    elif room and not room.online:
        parts.append(f"{c.room}: {c.room_label}, {room.type}, capacity {room.capacity} >= {headcount}")
        rule_ids += ["R-ROOM-FREE", "R-ROOM-CAP", "R-ROOM-TYPE"]
        latest = latest_end_for_physical(c.day)
        if latest is not None:
            parts.append(f"ends {hhmm(c.end)} <= {hhmm(latest)} (last shuttle - {settings.shuttle_buffer_min} min)")
            rule_ids.append("R-SHUTTLE")
    else:
        parts.append(f"online session kept online ({c.room})")
    if c.start in (510, 645, 810, 945, 1125):
        rule_ids.append("R-GRID")
    soft = [n for n in c.notes if not n.startswith("shuttle:")]
    if soft:
        parts.append("trade-offs: " + ", ".join(soft))
        rule_ids.append("R-LOAD")
    if dtype == DisruptionType.HOLIDAY:
        rule_ids.append("R-HOL")
    if dtype == DisruptionType.LECTURER_UNAVAILABLE:
        rule_ids.append("R-CLASH-LECT")
    return {
        "session_id": s.id,
        "module_name": s.module_name,
        "module_ids": s.module_ids,
        "lecturer_id": s.lecturer_id,
        "lecturer_name": s.lecturer_name,
        "substitute": substitutes.get(s.id) or substitutes.get("*"),
        "school": s.school,
        "students": headcount,
        "from": {"date": s.date.isoformat(), "start": s.start_iso(), "end": s.end_iso(), "room": s.room, "label": fmt_slot(s.date, s.start_min, s.end_min)},
        "to": {
            "date": c.day.isoformat(),
            "start": iso(c.day, c.start),
            "end": iso(c.day, c.end),
            "room": c.room,
            "online": c.room == "ONLINE",
            "label": fmt_slot(c.day, c.start, c.end),
        },
        "change": "room-only" if same_time else ("online" if c.room == "ONLINE" else "reschedule"),
        "affected_groups": [{"intake": i, "grouping": g} for i, g in s.groups],
        "rationale": "; ".join(parts) + ".",
        "rule_ids": sorted(set(rule_ids)),
        "cost": c.cost,
    }


# ------------------------------------------------------------------ views / explain
def proposal_view(p: dict, move_limit: Optional[int] = None) -> dict:
    out = dict(p)
    if move_limit is not None and len(p.get("moves", [])) > move_limit:
        out["moves"] = p["moves"][:move_limit]
        out["moves_truncated"] = len(p["moves"])
    return out


def explain_proposal(proposal_id: str) -> dict:
    p = get_store().get("proposals", proposal_id)
    if not p:
        raise NotFound("UNKNOWN_PROPOSAL", f"No proposal {proposal_id}")
    if p["kind"] != ProposalKind.REPLAN.value:
        return {"proposal_id": proposal_id, "kind": p["kind"], "status": p["status"], "text": p.get("explanation", p.get("title", ""))}
    s = p["summary"]
    lines = [
        f"**{p['title']}** - proposal {p['id']} v{p['version']} ({p['status']}).",
        f"{s['sessions']} sessions affected, {s['intake_groups']} intake groups, ~{s['students_affected']} students.",
        f"Placed in a physical room: {s['placed_physical']} ({s['share_physical']:.0%}); online fallback: {s['placed_online']}; "
        f"unresolved: {s['unresolved']}. Solved in {p['stats'].get('total_s')} s ({p['stats'].get('status')}); "
        f"automatic clash check: {'PASSED - zero group, lecturer or room clashes' if s['clash_check']['passed'] else 'FAILED'}.",
    ]
    table = []
    if p.get("bulk"):
        lines.append("By school:")
        for r in s.get("by_school", [])[:12]:
            lines.append(f"- {r['school']}: {r['sessions']} sessions -> {r['physical']} physical, {r['online']} online, {r['unresolved']} unresolved")
        lines.append("New days used: " + ", ".join(f"{k[5:]}: {v}" for k, v in s.get("by_new_day", {}).items()))
    else:
        for m in p["moves"]:
            table.append({
                "session": f"{m['module_name']} ({m['lecturer_id']})",
                "from": f"{m['from']['label']} {m['from']['room']}",
                "to": f"{m['to']['label']} {m['to']['room']}",
                "groups": ", ".join(f"{g['intake']}/{g['grouping']}" for g in m["affected_groups"][:4]) + (" ..." if len(m["affected_groups"]) > 4 else ""),
                "rules": ", ".join(m["rule_ids"]),
                "why": m["rationale"],
            })
    for u in p["unresolved"][:10]:
        lines.append(f"Unresolved: {u['session']['module_name']} {u['session']['time']} {u['session']['date']} - {u['reason']}. Options: {', '.join(u['options'])}.")
    lines.append("Rules applied: " + ", ".join(f"{c['id']} [{c['label']}]" for c in p["citations"]))
    lines.append("Nothing has been changed yet. Approve, edit (e.g. 'move the Thursday one to the afternoon') or reject?")
    return {"proposal_id": p["id"], "status": p["status"], "text": "\n".join(lines), "table": table, "citations": p["citations"]}


# ------------------------------------------------------------------ overlay of executed moves
def apply_moves_to_dataset(ds: Dataset, moves: list[dict], proposal_id: str) -> None:
    ds.__dict__.pop("_occ_cache", None)
    for m in moves:
        s = ds.sessions.get(m["session_id"])
        if not s:
            continue
        nd = date.fromisoformat(m["to"]["date"])
        ns = parse_iso(m["to"]["start"])
        ne = parse_iso(m["to"]["end"])
        ds.room_busy.remove(s.room, s.date, s.id)
        ds.lect_busy.remove(s.lecturer_id, s.date, s.id)
        for g in s.groups:
            ds.group_busy.remove(g, s.date, s.id)
        if s.id in ds.by_date.get(s.date, []):
            ds.by_date[s.date].remove(s.id)
        if s.id in ds.by_room.get(s.room, []):
            ds.by_room[s.room].remove(s.id)
        if s.orig_date is None:
            s.orig_date, s.orig_start_min, s.orig_room = s.date, s.start_min, s.room
        s.date, s.start_min, s.end_min = nd, ns.hour * 60 + ns.minute, ne.hour * 60 + ne.minute
        s.room = m["to"]["room"]
        s.moved_by = proposal_id
        lect = m.get("substitute") or s.lecturer_id
        if s.room not in ds.rooms:
            from ..data.catalog import build_room

            ds.rooms[s.room] = build_room(s.room)
        ds.by_date[s.date].append(s.id)
        ds.by_room[s.room].append(s.id)
        if s.room != "ONLINE":
            ds.room_busy.add(s.room, s.date, s.start_min, s.end_min, s.id)
        ds.lect_busy.add(lect, s.date, s.start_min, s.end_min, s.id)
        for g in s.groups:
            ds.group_busy.add(g, s.date, s.start_min, s.end_min, s.id)


def replay_executed() -> int:
    ds = get_dataset()
    n = 0
    for p in sorted(get_store().list("proposals", status=ProposalStatus.EXECUTED.value), key=lambda p: p["id"]):
        if p["kind"] == ProposalKind.REPLAN.value:
            apply_moves_to_dataset(ds, p["moves"], p["id"])
            n += 1
    return n
