"""In-app assistant: natural language -> the same service calls the MCP agents use -> reply text + rich UI cards.

The in-app assistant is a deterministic, offline intent parser for exactly the operations this product does
(disruptions, approvals/edits, slots, schedules, free rooms, attendance), so the demo never depends on the network.
Open-ended language is the job of the Gemini Enterprise agents (agents/), which call the same functions over MCP.
Human approval is preserved: planning only ever creates DRAFTs; only an explicit user "approve" (or the Approve
button) approves + executes, and only if the signed-in role may approve (identity.can_approve).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from ..config import MYT, settings
from ..data.loader import get_dataset
from ..domain import hhmm
from . import attendance, proposals, replan, rooms, slots, timetable
from .errors import ToolError
from .identity import Identity, can_approve, can_create_disruption
from .store import get_store

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
ROOM_RE = re.compile(r"\b([A-ES])-?(\d{2})-?(\d{2})\b", re.I)
STUDENT_RE = re.compile(r"\bSTU(?:-DEMO-\d{2}|\d{5})\b", re.I)


# ------------------------------------------------------------------ date parsing
def _today() -> date:
    return settings.now().date()


def parse_dates(text: str) -> tuple[Optional[date], Optional[date]]:
    """-> (start, end) inclusive. Understands today/tomorrow/day after tomorrow, weekday names, 'this/next week',
    '16 Nov', 'Nov 16', ISO dates, and 'until <day>'."""
    t = text.lower()
    today = _today()
    found: list[date] = []
    for m in re.finditer(r"\b(20\d\d)-(\d\d)-(\d\d)\b", t):
        found.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", t):
        found.append(date(today.year, MONTHS[m.group(2)], int(m.group(1))))
    for m in re.finditer(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\b", t):
        found.append(date(today.year, MONTHS[m.group(1)], int(m.group(2))))
    if "day after tomorrow" in t:
        found.append(today + timedelta(days=2))
    elif "tomorrow" in t:
        found.append(today + timedelta(days=1))
    if re.search(r"\btoday\b|this morning|this afternoon|right now", t):
        found.append(today)
    if "next week" in t:
        mon = today + timedelta(days=7 - today.weekday())
        return mon, mon + timedelta(days=4)
    if "this week" in t:
        return today, today + timedelta(days=4 - today.weekday()) if today.weekday() < 5 else today
    for i, wd in enumerate(WEEKDAYS):
        for m in re.finditer(rf"\b(next\s+)?{wd[:3]}(?:{wd[3:]})?\b", t):
            delta = (i - today.weekday()) % 7
            if m.group(1) and delta < 7:
                delta = delta + 7 if delta == 0 else delta
            found.append(today + timedelta(days=delta))
    until = re.search(r"\b(until|till|through|to)\b", t)
    if not found:
        return None, None
    found = sorted(set(found))
    if until and len(found) == 1:
        return today, found[0]
    return found[0], found[-1]


def parse_time(text: str) -> Optional[int]:
    t = text.lower()
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t)
    if m:
        h = int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0)
        return h * 60 + int(m.group(2) or 0)
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


# ------------------------------------------------------------------ entity extraction
def find_lecturers(text: str) -> list[str]:
    ds = get_dataset()
    out = []
    for tok in re.findall(r"\b[A-Z]{2,4}\b", text):
        if tok in ds.by_lecturer and tok not in out:
            out.append(tok)
    return out


def find_intakes(text: str) -> list[str]:
    ds = get_dataset()
    out = []
    for tok in re.findall(r"[A-Z0-9()]{6,}", text.upper()):
        for cand in (tok, tok.split("(")[0]):
            if cand in ds.by_intake and cand not in out and sum(ch.isdigit() for ch in cand) >= 4:
                out.append(cand)
                break
    return out


def find_rooms(text: str) -> list[str]:
    ds = get_dataset()
    out = []
    for m in ROOM_RE.finditer(text):
        name = f"{m.group(1).upper()}-{m.group(2)}-{m.group(3)}"
        if name in ds.rooms and name not in out:
            out.append(name)
    low = text.lower()
    for pat, prefix in ((r"auditorium\s*(\d)", "Auditorium {} "), (r"tech\s*lab\s*(\d-\d{2})", "Tech Lab {}"),
                        (r"discussion\s*room\s*(\d)", "Discussion Room {} "), (r"presentation\s*room\s*(\d)", "Presentation Room {} ")):
        for m in re.finditer(pat, low):
            pre = prefix.format(m.group(1)).lower()
            for name in ds.rooms:
                if name.lower().startswith(pre) and name not in out:
                    out.append(name)
                    break
    return out


# ------------------------------------------------------------------ cards
def _proposal_card(p: dict, who: Identity) -> dict:
    s = p.get("summary", {})
    dis = get_store().get("disruptions", p.get("disruption_id")) if p.get("disruption_id") else None
    try:
        can_approve(who, p, dis)
        approvable = p["status"] == "DRAFT"
    except ToolError:
        approvable = False
    moves = [{
        "type": m["type"], "session_id": m["session_id"], "module": m["module_name"], "lecturer": m["lecturer_id"],
        "substitute": m.get("substitute"), "substitute_name": m.get("substitute_name"),
        "from": m["from"], "to": m["to"], "groups": len(m["affected_groups"]), "students": m["students"],
        "rules": m["rule_ids"][:5], "why": m["rationale"], "school": m["school"],
    } for m in p.get("moves", [])[:8]]
    return {"type": "proposal", "id": p["id"], "version": p.get("version", 1), "kind": p["kind"], "title": p["title"],
            "status": p["status"], "summary": s, "stats": {k: p.get("stats", {}).get(k) for k in ("total_s", "status", "engine")},
            "moves": moves, "more_moves": max(0, len(p.get("moves", [])) - 8), "unresolved": [
                {"module": u["session"].get("module_name"), "when": f"{u['session'].get('date')} {u['session'].get('time')}", "reason": u["reason"]}
                for u in p.get("unresolved", [])[:5]],
            "can_approve": approvable, "booking": p.get("booking"),
            "citations": [{"id": c["id"], "title": c["title"], "label": c["label"]} for c in p.get("citations", [])][:8]}


def _impact_card(d: dict) -> dict:
    return {"type": "impact", "id": d["id"], "disruption_type": d["type"], "headline": d["headline"], "impact": d["impact"],
            "scope": d["scope"], "window": d["window"],
            "sessions": [{"module": s["module_name"], "date": s["date"], "time": s["time"], "room": s["room"], "groups": s["n_groups"]}
                         for s in d.get("affected_sessions", [])[:6]]}


def _sched_card(title: str, sessions: list[dict]) -> dict:
    return {"type": "schedule", "title": title, "sessions": [
        {"id": s["id"], "date": s["date"], "day": s["day"], "time": s["time"], "start": s["start"], "end": s["end"], "module": s["module_name"],
         "room": s["room"], "lecturer": s["lecturer_id"], "groups": s["n_groups"], "students": s.get("students"), "moved": bool(s.get("moved_by"))}
        for s in sessions[:40]]}


# ------------------------------------------------------------------ handlers
def _plan_lecturer(who: Identity, lid: str, a: date, b: date, reason: str) -> tuple[str, list[dict], dict]:
    d = replan.create_disruption("LECTURER_UNAVAILABLE", {"lecturer_id": lid}, {"start": a.isoformat(), "end": b.isoformat()}, reason, who.label)
    when = a.strftime("%a %d %b") + ("" if a == b else f" – {b.strftime('%a %d %b')}")
    if not d["impact"]["sessions"]:
        return f"Got it — {lid} is unavailable {when}, but there are no upcoming classes in that window. Nothing to re-plan.", [_impact_card(d)], {}
    p = replan.plan_replan(d["id"], {}, created_by=who.label)
    s = p["summary"]
    parts = []
    if s["substituted"]:
        parts.append(f"**{s['substituted']}** covered by a substitute who teaches the same module (same time and room — no student affected)")
    if s["rescheduled"]:
        parts.append(f"**{s['rescheduled']}** rescheduled to a clash-free slot")
    if s["placed_online"]:
        parts.append(f"**{s['placed_online']}** moved online")
    if s["unresolved"]:
        parts.append(f"**{s['unresolved']}** still need a decision")
    reply = (f"{'Sorry to hear that. ' if who.role == 'lecturer' else ''}{d['headline']} I've drafted a plan for {when}: " + "; ".join(parts)
             + f". Clash check passed in {p['stats']['total_s']}s. **Nothing has changed yet** — approve it, or tell me what to adjust "
               "(e.g. \"move it to the afternoon\" or \"don't use a substitute\").")
    return reply, [_impact_card(d), _proposal_card(p, who)], {"proposal_id": p["id"], "disruption_id": d["id"]}


def handle(message: str, who: Identity, ctx: Optional[dict] = None) -> dict:
    ctx = dict(ctx or {})
    text = message.strip()
    low = text.lower()
    ds = get_dataset()
    try:
        # ---------------- approvals / edits on the current proposal
        pid = ctx.get("proposal_id")
        if pid and re.search(r"^(yes|yep|ok(ay)?|approve|approved|go ahead|do it|confirm|looks good|sounds good)\b", low):
            p = proposals.get_proposal(pid)
            dis = get_store().get("disruptions", p.get("disruption_id")) if p.get("disruption_id") else None
            can_approve(who, p, dis)
            proposals.approve_proposal(pid, who.label)
            done = proposals.execute_proposal(pid, who=who.label)
            ex = done["execution"]
            a = ex["actions"]
            reply = (f"Approved and done. I created **{a.get('calendar_events', 0)} calendar event(s)**, **{a.get('gmail_drafts', 0)} Gmail draft(s)** "
                     f"(waiting in Gmail for a person to send) and a change-log entry. Everything is in the audit log.")
            return {"reply": reply, "cards": [{"type": "executed", "proposal_id": pid, "actions": a, "mode": ex.get("mode"),
                                               "links": {"calendar": ex.get("calendar", {}).get("bundle_url"), "drafts": ex.get("drafts", {}).get("index_url"),
                                                         "changelog": ex.get("changelog", {}).get("doc_url")},
                                               "drafts": [{"subject": d["subject"], "to": d["to"], "url": d["url"]} for d in ex.get("drafts", {}).get("drafts", [])[:6]]}],
                    "context": {}}
        if pid and re.search(r"^(no|reject|cancel|scrap|discard)\b", low):
            proposals.reject_proposal(pid, text, who=who.label)
            return {"reply": "Okay — I've rejected that plan. Nothing was changed.", "cards": [], "context": {}}
        if pid and (re.search(r"\b(afternoon|morning)\b", low) or re.search(r"\b(no|don.?t|without)\b.*\bsubstitute", low)):
            p = proposals.get_proposal(pid)
            opts = dict(p.get("options") or {})
            pins, declined = dict(opts.get("pins") or {}), list(opts.get("decline_substitutes") or [])
            day = next((i for i, w in enumerate(WEEKDAYS) if re.search(rf"\b{w}|\b{w[:3]}\b", low)), None)
            if re.search(r"\b(no|don.?t|without)\b.*\bsubstitute", low):
                declined += [m["session_id"] for m in p["moves"] if m["type"] == "SUBSTITUTE"]
            period = "afternoon" if "afternoon" in low else ("morning" if "morning" in low else None)
            if period:
                for m in p["moves"]:
                    if m["type"] == "SUBSTITUTE":
                        continue
                    if day is None or date.fromisoformat(m["from"]["date"]).weekday() == day or date.fromisoformat(m["to"]["date"]).weekday() == day:
                        pins[m["session_id"]] = {"period": period}
            opts.update({"pins": pins, "decline_substitutes": declined})
            p2 = replan.plan_replan(p["disruption_id"], opts, created_by=who.label)
            s = p2["summary"]
            return {"reply": f"Updated (v{p2['version']}): {s['substituted']} substitute, {s['rescheduled']} rescheduled, {s['placed_online']} online, "
                             f"{s['unresolved']} unresolved. Still clash-free. Approve this version?",
                    "cards": [_proposal_card(p2, who)], "context": {"proposal_id": p2["id"], "disruption_id": p2["disruption_id"]}}

        a, b = parse_dates(text)
        # ---------------- holiday
        if re.search(r"\b(public holiday|holiday|campus (is )?closed|no classes)\b", low) and not re.search(r"\b(sick|ill|unwell)\b", low):
            if not a:
                return {"reply": "Which date is the holiday? For example: \"Monday 16 Nov is a public holiday\".", "cards": [], "context": ctx}
            can_create_disruption(who, "HOLIDAY", {})
            d = replan.create_disruption("HOLIDAY", {"date": a.isoformat(), "name": "Declared public holiday"}, None, text, who.label)
            p = replan.plan_replan(d["id"], {}, created_by=who.label)
            s = p["summary"]
            top = ", ".join(f"{r['school']} {r['sessions']}" for r in s.get("by_school", [])[:4])
            reply = (f"{d['headline']} I re-planned the whole campus in **{p['stats']['total_s']}s**: **{s['placed_physical']}** stay in a room "
                     f"({s['share_physical']:.0%}), **{s['placed_online']}** go online (mostly evening classes — the last regular shuttle is 19:15), "
                     f"**{s['unresolved']}** need a decision. Largest schools: {top}. Zero clashes. Review it on the live board or approve here.")
            return {"reply": reply, "cards": [_impact_card(d), _proposal_card(p, who)], "context": {"proposal_id": p["id"], "disruption_id": d["id"]}}

        # ---------------- room unavailable
        rms = find_rooms(text)
        if rms and re.search(r"\b(flood|leak|closed|unavailable|broken|out of (order|service)|maintenance|can.?t be used|not available|no power|aircon)\w*", low):
            can_create_disruption(who, "ROOM_UNAVAILABLE", {})
            end = b or (_today() + timedelta(days=1))
            d = replan.create_disruption("ROOM_UNAVAILABLE", {"rooms": rms}, {"start": settings.now().isoformat(), "end": end.isoformat()}, text, who.label)
            if not d["impact"]["sessions"]:
                return {"reply": f"{', '.join(rms)} has no upcoming classes until {end.strftime('%a %d %b')} — nothing to move.", "cards": [_impact_card(d)], "context": {}}
            p = replan.plan_replan(d["id"], {}, created_by=who.label)
            s = p["summary"]
            reply = (f"{d['headline']} **{s['room_only_changes']}** keep their time and just switch room; **{s['rescheduled'] - s['room_only_changes']}** move to a new slot"
                     f"{', ' + str(s['placed_online']) + ' online' if s['placed_online'] else ''}. Clash-free. Approve?")
            return {"reply": reply, "cards": [_impact_card(d), _proposal_card(p, who)], "context": {"proposal_id": p["id"], "disruption_id": d["id"]}}

        # ---------------- lecturer unavailable
        if re.search(r"\b(sick|ill|unwell|mc\b|medical|can.?t (make it|teach|come)|cannot (teach|come)|unavailable|away|leave|emergency|not (be )?(in|available|coming))\b", low):
            lects = find_lecturers(text)
            if who.role == "lecturer" and (not lects or lects == [who.user] or re.search(r"\b(i|i'm|im|my|me)\b", low)):
                lid = who.user
            elif who.role in ("admin", "agent") and lects:
                lid = lects[0]
            elif who.role == "student":
                raise ToolError("ROLE_FORBIDDEN", "Only lecturers or the timetabling office can report a lecturer as unavailable.")
            else:
                return {"reply": "Which lecturer is unavailable? Give me their ID (for example MZD).", "cards": [], "context": ctx}
            can_create_disruption(who, "LECTURER_UNAVAILABLE", {"lecturer_id": lid})
            a = a or _today()
            b = b or a
            reply, cards, c = _plan_lecturer(who, lid, a, b, text)
            return {"reply": reply, "cards": cards, "context": c}

        # ---------------- slot finder
        if re.search(r"\b(find|schedule|book|arrange|set up|organi[sz]e)\b", low) and re.search(r"\b(slot|time|viva|vivas|presentation|meeting|talk|session|class|make-?up|event|exam)\w*", low):
            if who.role == "student":
                raise ToolError("ROLE_FORBIDDEN", "Booking slots is for lecturers and the timetabling office.")
            lects = find_lecturers(text)
            intakes = find_intakes(text)
            if who.role == "lecturer" and who.user not in lects and re.search(r"\b(i|me|my)\b", low):
                lects = [who.user] + lects
            dur = 120
            m = re.search(r"(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|min|mins|minute|minutes)\b", low)
            if m:
                dur = int(float(m.group(1)) * (60 if m.group(2).startswith("h") else 1))
            count = 1
            m = re.search(r"\b(\d{1,2})\s+(vivas|presentations|sessions|slots|students)\b", low)
            if m:
                count = int(m.group(1))
            if "viva" in low and dur == 120:
                dur = 45
            rtype = next((t for k, t in [("presentation", "presentation"), ("viva", "presentation"), ("auditorium", "auditorium"), ("talk", "auditorium"),
                                          ("lab", "lab"), ("discussion", "discussion"), ("meeting", "discussion"), ("online", "online"), ("classroom", "classroom")] if k in low), None)
            if not lects and not intakes:
                return {"reply": "Who needs to be there? Give me the examiners' lecturer IDs and/or the intake codes.", "cards": [], "context": ctx}
            wa = a or (_today() + timedelta(days=1))
            wb = b if b and b > wa else wa + timedelta(days=6)
            r = slots.find_common_slots(intakes, lects, dur, {"start": wa.isoformat(), "end": wb.isoformat()}, {"type": rtype} if rtype else None, count)
            title = ("FYP vivas" if "viva" in low else "Guest talk" if "talk" in low else "Meeting") + (f" - {', '.join(intakes)}" if intakes else "")
            if not r["options"]:
                return {"reply": f"No common slot between {wa:%d %b} and {wb:%d %b}. Blocked mostly by: " + ", ".join(f"{k} ×{v}" for k, v in r["eliminated"].items())
                                 + ". Try a wider window, another room type, or fewer people.", "cards": [], "context": ctx}
            reply = (f"Found **{r['feasible_slots']}** feasible start times; here are the best 3 where "
                     + " and ".join(x for x in [f"{', '.join(lects)}" if lects else "", f"{', '.join(intakes)}" if intakes else ""] if x)
                     + f" are all free ({count} × {dur} min{', ' + rtype + ' room' if rtype else ''}). Pick one and I'll draft the invites for approval.")
            return {"reply": reply, "cards": [{"type": "slots", "title": title, "groups": intakes, "lecturers": lects, "options": r["options"], "request": r["request"]}],
                    "context": ctx}

        # ---------------- attendance
        if re.search(r"\b(miss|absen|attendance|skip)\w*", low):
            sid = None
            m = STUDENT_RE.search(text)
            if m:
                sid = m.group(0).upper()
            elif who.role == "student":
                sid = who.user
            if who.role == "student" and sid != who.user:
                raise ToolError("ROLE_FORBIDDEN", "You can only see your own attendance.")
            if not sid:
                return {"reply": "Which student? Give me their ID (e.g. STU-DEMO-01).", "cards": [], "context": ctx}
            f = attendance.attendance_forecast(sid)
            return {"reply": f["message"], "cards": [{"type": "attendance", **{k: f[k] for k in (
                "student_id", "name", "intake", "grouping", "current_percent", "remaining_sessions", "max_more_absences", "binding_module",
                "projected_percent_end", "threshold", "trend", "next_class")}, "per_module": f["per_module"],
                "weekly": [w["cumulative_percent"] for w in f["weekly"]]}], "context": ctx}

        # ---------------- free rooms
        if re.search(r"\b(free|empty|available|vacant)\b", low) and re.search(r"\b(room|lab|auditorium|classroom|space)", low):
            d0 = a or _today()
            t = parse_time(text) or (settings.now().hour * 60 + settings.now().minute if d0 == _today() else 10 * 60)
            st = datetime(d0.year, d0.month, d0.day, t // 60, t % 60, tzinfo=MYT)
            rtype = next((x for x in ("lab", "auditorium", "discussion", "presentation", "classroom") if x in low), None)
            cap = re.search(r"(\d{2,3})\s*(people|students|seats|pax)", low)
            r = rooms.find_free_rooms(st.isoformat(), (st + timedelta(hours=1)).isoformat(), int(cap.group(1)) if cap else 0, rtype, 30)
            return {"reply": f"**{r['count']}** {rtype or 'physical'} room(s) are free {st:%a %d %b} {hhmm(t)}–{hhmm(t + 60)}.",
                    "cards": [{"type": "rooms", "title": f"Free {st:%a %d %b} {hhmm(t)}–{hhmm(t + 60)}", "rooms": r["rooms"][:24], "count": r["count"]}], "context": ctx}

        # ---------------- schedule
        if re.search(r"\b(timetable|schedule|classes|class|teaching|lectures|what do i have|what.?s on|my week|my day)\b", low):
            a = a or _today()
            b = b or (a + timedelta(days=4) if "week" in low else a)
            if who.role == "student":
                st = attendance.get_student_record(who.user)
                r = timetable.get_group_schedule(st["intake"], st["grouping"], a.isoformat(), b.isoformat())
                who_txt = f"{st['intake']}/{st['grouping']}"
            else:
                lects = find_lecturers(text)
                lid = (lects[0] if lects else who.user) if who.role != "lecturer" or not lects else lects[0]
                if not lid:
                    return {"reply": "Whose timetable? Give me a lecturer ID.", "cards": [], "context": ctx}
                r = timetable.get_lecturer_schedule(lid, a.isoformat(), b.isoformat())
                who_txt = lid
            n = r["count"]
            span = a.strftime("%a %d %b") + ("" if a == b else f" – {b.strftime('%a %d %b')}")
            return {"reply": f"{who_txt} has **{n}** session{'s' if n != 1 else ''} {span}." + (" Moved sessions are highlighted." if any(s.get("moved_by") for s in r["sessions"]) else ""),
                    "cards": [_sched_card(f"{who_txt} · {span}", r["sessions"])], "context": ctx}

        return {"reply": _help(who), "cards": [], "context": ctx}
    except ToolError as e:
        return {"reply": f"I couldn't do that: {e.message}", "cards": [{"type": "error", "code": e.code, "message": e.message, "details": e.details}], "context": ctx}


def _help(who: Identity) -> str:
    if who.role == "student":
        return "I can tell you **how many more classes you can miss**, show **your timetable** (\"what do I have tomorrow?\") and what changed."
    if who.role == "lecturer":
        return ("Tell me in plain words — e.g. **\"I'm sick tomorrow\"**, **\"find a 45-minute slot next week for 6 vivas with CMM, MSB and RJR\"**, "
                "**\"what do I have on Friday?\"** or **\"which rooms are free at 3pm?\"**. I draft a plan; nothing changes until you approve.")
    return ("Try **\"Lecturer MZD is sick tomorrow\"**, **\"Room B-04-03 is flooded until Friday\"**, **\"Monday 16 Nov is a public holiday\"**, "
            "**\"find a 2 hour slot next week for AFCF2509BA and AFCF2609BA in an auditorium\"** or **\"which labs are free at 2pm?\"**.")


def suggestions(who: Identity) -> list[str]:
    if who.role == "student":
        return ["How many more classes can I miss?", "What do I have tomorrow?", "What's my timetable this week?"]
    if who.role == "lecturer":
        return ["I'm sick tomorrow, sort out my classes", "What do I have this week?",
                "Find a 45 minute slot next week for 6 vivas with CMM, MSB and RJR", "Which rooms are free at 3pm?"]
    return ["Lecturer MZD is sick tomorrow", "Room B-04-03 is flooded until Friday", "Monday 16 Nov is now a public holiday",
            "Which labs are free at 2pm tomorrow?"]


def engine_name() -> str:
    return "rules"
