"""Slot Finder: slots where student groups + 2-3 examiners/lecturers + a suitable room are all free.
Reuses the same busy indexes, holiday, notice and shuttle rules as the re-planner."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Optional

from ..config import DAY_END_MIN, DAY_START_MIN, EVENING_START_MIN, MYT, STANDARD_STARTS, TICK_MIN, settings
from ..data.loader import Dataset, get_dataset
from ..domain import ProposalKind, ProposalStatus, hhmm, iso
from .audit import log_event
from .errors import NotFound, ToolError, require
from .holidays import is_working_day
from .policy import cite
from .shuttle import latest_end_for_physical
from .store import get_store
from .timetable import parse_date
from .workspace import CalendarEvent, Draft, addr_intake, addr_lecturer, get_workspace, new_uid


def _resolve_groups(ds: Dataset, groups: list) -> list[tuple[str, str]]:
    out = []
    for g in groups or []:
        if isinstance(g, str):
            intake, grouping = (g.split("/") + [None])[:2] if "/" in g else (g, None)
        else:
            intake, grouping = g.get("intake"), g.get("grouping")
        intake = (intake or "").upper().strip()
        if intake not in ds.by_intake:
            from .timetable import _intake_suggest

            raise NotFound("UNKNOWN_INTAKE", f"No intake '{intake}'", suggestions=_intake_suggest(ds, intake))
        gs = [grouping.upper()] if grouping else sorted(ds.by_intake[intake])
        out += [(intake, x) for x in gs]
    return sorted(set(out))


def find_common_slots(
    groups: list,
    lecturer_ids: list[str],
    duration_min: int,
    window: dict,
    room_requirements: Optional[dict] = None,
    count: int = 1,
    top_n: int = 3,
    gap_min: int = 0,
) -> dict:
    """Ranked candidate slots. count>1 finds a contiguous block (e.g. 6 vivas of 45 min back-to-back, same room + panel)."""
    ds = get_dataset()
    require(15 <= int(duration_min) <= 480, "BAD_DURATION", "duration_min must be 15..480")
    require(1 <= int(count) <= 12, "BAD_COUNT", "count must be 1..12")
    gs = _resolve_groups(ds, groups)
    lects = [l.upper().strip() for l in (lecturer_ids or [])]
    for l in lects:
        if l not in ds.by_lecturer:
            from .timetable import _lect_suggest

            raise NotFound("UNKNOWN_LECTURER", f"No lecturer '{l}'", suggestions=_lect_suggest(ds, l))
    require(gs or lects, "EMPTY", "give at least one group or lecturer")
    rr = room_requirements or {}
    rtype = rr.get("type")
    online = rtype == "online" or rr.get("online") is True
    headcount = int(rr.get("min_capacity") or 0)
    if not headcount and gs:
        headcount = sum(ds.group_sizes.get(g, 0) for g in gs) + len(lects) if count == 1 else 1 + len(lects)
    a = parse_date((window or {}).get("start") or settings.now().date())
    b = parse_date((window or {}).get("end") or (a + timedelta(days=7)))
    require(a <= b and (b - a).days <= 31, "BAD_WINDOW", "window must be <= 31 days")
    earliest = settings.now() + timedelta(hours=settings.notice_hours)
    block = int(duration_min) * int(count) + int(gap_min) * (int(count) - 1)

    starts = sorted(set(STANDARD_STARTS) | set(range(DAY_START_MIN, DAY_END_MIN, 4 * TICK_MIN)) | set(range(DAY_START_MIN, DAY_END_MIN, 45)))
    cands, elim = [], Counter()
    d = a
    while d <= b:
        if not is_working_day(d):
            d += timedelta(days=1)
            continue
        if d > ds.dates[-1]:
            elim["beyond published timetable"] += 1
        latest = DAY_END_MIN if online else latest_end_for_physical(d)
        for st in starts:
            en = st + block
            if latest is None or en > (latest if not online else DAY_END_MIN):
                elim["after last shuttle / day end (R-SHUTTLE)"] += 1
                continue
            if datetime(d.year, d.month, d.day, st // 60, st % 60, tzinfo=MYT) < earliest:
                elim["notice period (R-NOTICE)"] += 1
                continue
            busy_l = [l for l in lects if not ds.lect_busy.is_free(l, d, st, en)]
            if busy_l:
                elim["examiner/lecturer busy"] += 1
                continue
            busy_g = [g for g in gs if not ds.group_busy.is_free(g, d, st, en)]
            if busy_g:
                elim["student group busy"] += 1
                continue
            rooms = []
            if online:
                rooms = ["ONLINE"]
            else:
                for r in ds.rooms.values():
                    if r.online or (rtype and r.type != rtype) or r.capacity < headcount:
                        continue
                    if ds.room_busy.is_free(r.name, d, st, en):
                        rooms.append(r.name)
                rooms.sort(key=lambda n: (ds.rooms[n].capacity, n))
            if not rooms:
                elim["no suitable room free"] += 1
                continue
            score, why = 100.0, []
            days_out = (d - a).days
            score -= days_out * 2
            if st in STANDARD_STARTS:
                score += 6
                why.append("standard slot")
            if st >= EVENING_START_MIN:
                score -= 20
                why.append("evening")
            if 12 * 60 + 45 <= st < 13 * 60 + 30:
                score -= 5
                why.append("over lunch")
            load = []
            for g in gs:
                mins = ds.group_busy.busy_minutes(g, d)
                if mins + block > 360:
                    load.append(g)
            if load:
                score -= 4 * min(5, len(load))
                why.append(f"{len(load)} group(s) would exceed 6h that day")
            else:
                why.append("no group exceeds 6h that day")
            for l in lects:
                ivs = ds.lect_busy.intervals(l, d)
                if any(abs(s - en) <= 15 or abs(st - e) <= 15 for s, e, _ in ivs):
                    score -= 1
            cands.append({
                "date": d.isoformat(), "day": d.strftime("%a"), "start": iso(d, st), "end": iso(d, en),
                "label": f"{d.strftime('%a %d %b')} {hhmm(st)}-{hhmm(en)}",
                "rooms": rooms[:5], "room": rooms[0], "score": round(score, 1),
                "reason": f"All {len(gs)} group(s) and {len(lects)} examiner(s) free; {rooms[0]}" + (f" (cap {ds.rooms[rooms[0]].capacity} >= {headcount})" if not online else "") + "; " + ", ".join(why),
                "sub_slots": [{"start": iso(d, st + i * (int(duration_min) + int(gap_min))), "end": iso(d, st + i * (int(duration_min) + int(gap_min)) + int(duration_min))} for i in range(int(count))] if count > 1 else None,
            })
        d += timedelta(days=1)
    cands.sort(key=lambda c: (-c["score"], c["start"]))
    # diversify: at most one option per day in the top list
    top, seen = [], set()
    for c in cands:
        if c["date"] in seen:
            continue
        top.append(c)
        seen.add(c["date"])
        if len(top) >= int(top_n):
            break
    for i, c in enumerate(top, 1):
        c["rank"] = i
    return {
        "request": {"groups": [{"intake": i, "grouping": g} for i, g in gs], "lecturer_ids": lects, "duration_min": duration_min,
                    "count": count, "window": {"start": a.isoformat(), "end": b.isoformat()}, "room_requirements": rr, "headcount": headcount},
        "feasible_slots": len(cands),
        "options": top,
        "eliminated": dict(elim.most_common(6)),
        "citations": cite(["R-CLASH-GROUP", "R-CLASH-LECT", "R-ROOM-FREE", "R-ROOM-CAP", "R-NOTICE", "R-HOL", "R-SHUTTLE", "R-HITL"]),
    }


def create_slot_proposal(title: str, slot: dict, groups: list, lecturer_ids: list[str], room: Optional[str] = None,
                         description: str = "", created_by: str = "agent") -> dict:
    """Turn a chosen slot into a DRAFT SLOT_BOOKING proposal (invites + drafts only after approval)."""
    ds = get_dataset()
    require(slot and slot.get("start") and slot.get("end"), "BAD_SLOT", "slot must have start and end")
    gs = _resolve_groups(ds, groups)
    lects = [l.upper() for l in lecturer_ids or []]
    room = room or slot.get("room") or "ONLINE"
    from ..domain import parse_iso

    s, e = parse_iso(slot["start"]), parse_iso(slot["end"])
    d, sm, em = s.date(), s.hour * 60 + s.minute, e.hour * 60 + e.minute
    clashes = []
    if room != "ONLINE" and not ds.room_busy.is_free(room, d, sm, em):
        clashes.append(f"room {room} busy")
    clashes += [f"lecturer {l} busy" for l in lects if not ds.lect_busy.is_free(l, d, sm, em)]
    clashes += [f"group {g[0]}/{g[1]} busy" for g in gs if not ds.group_busy.is_free(g, d, sm, em)]
    if clashes:
        raise ToolError("SLOT_NO_LONGER_FREE", "Slot is no longer free", clashes=clashes)
    st = get_store()
    pid = st.next_id("PRO")
    p = {
        "id": pid, "kind": ProposalKind.SLOT_BOOKING.value, "status": ProposalStatus.DRAFT.value, "version": 1,
        "title": title or "Slot booking", "created_at": settings.now().isoformat(), "created_by": created_by,
        "booking": {"start": slot["start"], "end": slot["end"], "room": room, "sub_slots": slot.get("sub_slots"),
                    "groups": [{"intake": i, "grouping": g} for i, g in gs], "lecturer_ids": lects, "description": description},
        "summary": {"label": f"{d.strftime('%a %d %b')} {hhmm(sm)}-{hhmm(em)} {room}", "groups": len(gs), "lecturers": len(lects)},
        "citations": cite(["R-CLASH-GROUP", "R-CLASH-LECT", "R-ROOM-FREE", "R-HITL"]),
        "moves": [], "unresolved": [],
    }
    st.put("proposals", pid, p)
    log_event(created_by, "proposal.drafted", pid, after=p["summary"])
    return p


def execute_slot_booking(p: dict, who: str) -> dict:
    ds = get_dataset()
    ws = get_workspace()
    b = p["booking"]
    subs = b.get("sub_slots") or [{"start": b["start"], "end": b["end"]}]
    att = [addr_lecturer(l) for l in b["lecturer_ids"]] + [addr_intake(g["intake"], g["grouping"]) for g in b["groups"]]
    events = [CalendarEvent(summary=p["title"] + (f" #{i}" if len(subs) > 1 else ""), start=s["start"], end=s["end"],
                            location=b["room"], description=(b.get("description") or "") + f"\nBooked via Campus Time Ops, proposal {p['id']}, approved by {p.get('approved_by')}.",
                            attendees=att, uid=new_uid(p["id"] + f"-{i}")) for i, s in enumerate(subs, 1)]
    cal = ws.create_events(p["id"], events)
    body = f"Hello,\n\n{p['title']} is scheduled for {p['summary']['label']}.\n" + ("\n".join(f"- slot {i}: {s['start'][11:16]}-{s['end'][11:16]}" for i, s in enumerate(subs, 1)) if len(subs) > 1 else "") + "\n\nA calendar invite has been added.\n"
    drafts = ws.create_drafts(p["id"], [Draft(to=att[:10], bcc=att[10:], subject=f"Invitation: {p['title']} - {p['summary']['label']}", body=body)])
    from ..domain import parse_iso

    s, e = parse_iso(b["start"]), parse_iso(b["end"])
    _apply_booking(ds, p["id"], b)
    log_event(who, "calendar.events_created", p["id"], after={"count": cal["count"]})
    log_event(who, "gmail.drafts_created", p["id"], after={"count": drafts["count"]})
    return {"mode": ws.mode, "actions": {"calendar_events": cal["count"], "gmail_drafts": drafts["count"]}, "calendar": cal, "drafts": drafts,
            "draft_ids": [d["id"] for d in drafts["drafts"]]}


def _apply_booking(ds: Dataset, pid: str, b: dict) -> None:
    from ..domain import parse_iso

    s, e = parse_iso(b["start"]), parse_iso(b["end"])
    d, sm, em = s.date(), s.hour * 60 + s.minute, e.hour * 60 + e.minute
    bid = f"BOOK-{pid}"
    if b["room"] != "ONLINE":
        ds.room_busy.add(b["room"], d, sm, em, bid)
    for l in b["lecturer_ids"]:
        ds.lect_busy.add(l, d, sm, em, bid)
    for g in b["groups"]:
        ds.group_busy.add((g["intake"], g["grouping"]), d, sm, em, bid)


def replay_bookings() -> int:
    ds = get_dataset()
    n = 0
    for p in get_store().list("proposals", status=ProposalStatus.EXECUTED.value):
        if p["kind"] == ProposalKind.SLOT_BOOKING.value:
            _apply_booking(ds, p["id"], p["booking"])
            n += 1
    return n
