# SCOPE CHANGE — trim "Campus Time Ops" (apply on top of BUILD_PROMPT.md)

> This amends the build prompt you already have. **This document wins wherever the two conflict.** Apply it whether or not you've started building. If code, tests, data, docs or UI already exist for anything marked REMOVE, delete it completely: no dead routes, unused tools, stale tests or leftover menu items. Record the change in `docs/DECISIONS.md` as "Scope trim v2".

## Why
The product has to tell **one story: APU's live timetable, re-planned and optimised by agents with a human approving every step.** Anything that isn't about *time, rooms and who's where* dilutes that pitch, depends on unverifiable assumptions, or turns into a generic chatbot. Every feature that stays must run on the real timetable data.

---

## 1. REMOVE completely

| # | What | Where in BUILD_PROMPT.md | Action |
|---|---|---|---|
| R1 | **Passport reading, MRZ parsing and check-digit validation** | §6 `parse_passport_image`, §9 passport images, §10 passport upload, §11 `mrz.py`, `data/demo_passports/`, §14 MRZ criterion | Delete the tool, service, tests, sample images, UI and acceptance criterion |
| R2 | **Visa / student-pass renewal planning** (pass and passport expiry dates, working backwards from the renewal deadline) | §6 visa tools, §9 expiry fields | Delete. Synthetic students no longer have `pass_expiry`, `passport_expiry` or `nationality` |
| R3 | **The escalation ladder** (nudge → advisor meeting → formal warning letter → International Office approval, letter templates in Docs) | §6 `plan_escalation`, §7.3 | Delete |
| R4 | **The Visa Guardian agent as a separate scheduled workflow agent**, the 09:00 digest and the Google Chat digest | §7.3, §3 diagram | Delete the agent folder `agents/visa_guardian/`. It's replaced by the small attendance feature in §2 (K1) |
| R5 | **The Ops Q&A agent** (generic chatbot) | §7.4, `agents/ops_qa/` | Delete. It's the generic chatbot we're deliberately avoiding |
| R6 | **Energy / kWh / RM savings estimates** | §10 page 6, §13.2 | Delete the energy calculations and their assumption settings. Keep room utilisation (see K3) |
| R7 | **Mock exam data** `data/exams_mock.json` | §4.3 | Delete. Slot Finder doesn't need it |
| R8 | **"International student" framing and immigration wording** everywhere: UI labels, agent instructions, policy file, README, demo script | global | Remove. The attendance feature applies to **all** students |

---

## 2. KEEP but SHRINK

**K1 — Visa Guardian → "Attendance Risk" (a small feature, not an agent)**
- **Keep:** `get_attendance(student_id)` and `attendance_forecast(student_id)`, which return:
  - the current %
  - the trend
  - the projected % at the end of term
  - the **remaining sessions for the student's group from the real timetable**
  - `max_more_absences` against `ATTENDANCE_THRESHOLD` (default 0.80, configurable, labelled as an APU attendance-rule assumption to **VERIFY**)
- **Keep:** `attendance_risk_list(date)` (renamed from `visa_risk_sweep`). It's a ranked list of students below or heading towards the threshold. It is read-only and takes no actions.
- **UI:** one dashboard page, "Attendance Risk": a risk table plus a drill-down with the forecast chart and the "you can miss at most N more classes" figure. No escalation UI.
- **Chat:** add **one** capability to the Replan agent's instructions (no new agent): *"How many more classes can student X / I miss?"* → answers using `attendance_forecast`.
- **Synthetic students:** reduce to the fields `id, synthetic name, intake, grouping, attendance_records`. Keep about 3,000 students and the attendance profiles, plus at least 3 demo students for the hand-calculation test.

**K2 — Slot Finder:** keep it fully as specified (§7.2). It reuses the solver and is core to the story.

**K3 — Rooms page (was "Rooms & Energy"):** rename it **"Rooms"**. Keep the room × hour utilisation heatmap, the "empty rooms right now" list, and utilisation % per block. This is real data, and Replan and Slot Finder use the same free-room index.

**K4 — Timetable Health:** keep it as a **dashboard page only** (no agent): long gaps, groups with more than 3 back-to-back sessions, days over 6 hours, lecturer load, and the online vs physical session mix by time of day.

---

## 3. ADD (strengthens the core)

**A1 — Substitute lecturer finder (part of Replan, high priority)**
- A new tool `find_substitutes(session_id)`: lecturers who teach the **same module** (match on the `MODID` base, the code before the section suffix, and/or `MODULE_NAME`) across the timetable, are **free** for that session's time slot, and don't go over a configurable daily load (default 3 sessions per day). Rank by: teaches the same module section > the same module > the same programme prefix; then lowest load that day.
- Change `plan_replan` for `LECTURER_UNAVAILABLE`. For each affected session, first try a substitute (the session stays at the same time and room, so no student is affected). Only reschedule through the solver if no substitute exists or the user declines. Each move in the proposal shows its type: `SUBSTITUTE` or `RESCHEDULE` or `ONLINE` or `UNRESOLVED`.
- Executing it: for `SUBSTITUTE`, update the calendar event's lecturer and draft an email to the substitute asking them to confirm, plus a short notice to the affected groups.
- Add solver and service tests: the substitute is genuinely free and genuinely teaches the module.

**A2 — `send_drafts`: one-click sending (KEEP, with safeguards)**
Keep `send_drafts(proposal_id)` from §6. It sends the Gmail drafts that `execute_proposal` created. The default behaviour stays **drafts only**. Sending is a separate, deliberate step:
- **Gate:** it works only if the proposal is `EXECUTED` *and* a second explicit confirmation is given. In the dashboard, a "Send N emails" button opens a modal listing the recipients, the subject and a preview, and the user must click "Confirm send". In chat, the agent must ask "Send these N emails now?" and get an explicit yes. Approving the plan never sends anything by itself.
- **Recipient allowlist:** it sends only to addresses in the demo Workspace domain (`WORKSPACE_DEMO_DOMAIN`). Any other recipient is refused and logged. Enforce this on the server, not just in the UI.
- **Kill switch:** an `ALLOW_SEND=false` env flag (default `false` in `.env.example`, set to `true` only for the demo environment). When it's off, the button is hidden and the tool returns a clear error.
- **Limits:** at most 50 emails per call. Idempotent: drafts that were already sent are skipped, and the same proposal is never sent twice.
- **Audit:** log every send (who confirmed it, when, the recipients, the Gmail message IDs) as an `AuditEvent`, and show it on the Proposal detail page ("Sent 9/9 at 10:42 by prog.leader@…").
- **Tests:** refused without confirmation; refused when `ALLOW_SEND=false`; refused for recipients outside the allowlist; a second call on the same proposal sends nothing.

---

## 4. Updated agent list
Only **two** agents now:
1. **Replan** (hero): disruptions, substitute finder, rescheduling, approval, then Calendar, Gmail drafts and the change-log Doc, then optional one-click sending with confirmation (A2). It also answers attendance questions (K1).
2. **Slot Finder:** vivas, presentations, make-up classes, events.

Update the architecture diagram in `docs/ARCHITECTURE.md` and the README to match.

## 5. Updated dashboard pages
Overview · Disruptions (live re-plan animation) · Proposal detail (approve/edit/reject) · Slot Finder · **Rooms** · **Timetable Health** · **Attendance Risk** · Audit log.
Remove all visa, passport, energy and escalation UI and their navigation entries. The Overview KPI tiles become: sessions re-planned, substitutes found, median time to re-plan, pending approvals, students below the attendance threshold.

## 6. Updated build order
M0–M6 are unchanged, plus **A1 goes into M3/M5** (the substitute finder is part of the hero).
⇒ Freeze and tag `v1-hero`.
Then: **M7 Slot Finder → M8 Attendance Risk (½ day) → M9 Rooms + Timetable Health (½ day) → M10 Deploy → M11 Demo and report.**
If time runs short, cut in this order: M9 → M8 → M7. **Never cut M0–M6 or A1.**

## 7. Updated demo script (`docs/DEMO_SCRIPT.md`, 10 minutes)
| Time | Segment |
|---|---|
| 0:00–1:00 | **Problem.** Real APU timetable numbers, how disruptions are handled today (interview quote), APSpace shows timetables but doesn't re-plan them |
| 1:00–2:00 | **Architecture.** Real data, real rules, real engineering, human approval |
| 2:00–4:15 | **Replan, small.** "I'm sick tomorrow" → **substitutes found for 2 sessions**, 1 rescheduled with no clashes → edit → approve → Calendar, Gmail drafts and change log appear → "Send 9 emails" → confirm → emails arrive in a demo student's inbox on screen |
| 4:15–6:00 | **Replan, the wow moment.** "Monday is now a public holiday" → the grid turns red (~300–600 physical sessions) → the solver turns it green → summary by faculty, online fallback, the shuttle rule enforced |
| 6:00–7:30 | **Slot Finder.** Viva scheduling with 3 examiners → ranked slots → invites |
| 7:30–8:30 | **Insights.** Rooms heatmap, Timetable Health, Attendance Risk ("can miss at most 2 more classes", calculated from real remaining sessions) |
| 8:30–10:00 | **Impact and scale.** Measured metrics, privacy and the human approval step, roadmap (APSpace integration, other universities, enterprise shift and room planning) |

## 8. Updated acceptance criteria (replaces the affected items in §14)
- **Remove:** the MRZ criterion and anything about visa or escalation.
- **Add:** `find_substitutes` never returns a lecturer who has a clash or doesn't teach the module (tested).
- **Add:** in the "I'm sick tomorrow" demo, at least one session is resolved by a substitute and at least one by rescheduling, using the committed snapshot. Choose the demo lecturer so this holds, and record their `LECTID` in `docs/DEMO_SCRIPT.md`.
- **Keep:** the attendance "max more absences" figure matches a hand calculation for 3 test students.
- **Add:** `send_drafts` passes all the A2 tests. With `ALLOW_SEND=false` nothing can be sent from the UI or chat.
- **Add:** a search across the repo, UI and docs for `passport`, `MRZ`, `visa`, `EMGS`, `escalation`, `kWh` and `energy` returns nothing (except this decision note in `DECISIONS.md`).

## 9. Docs to update
`README.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` (Scope trim v2 and why), `docs/DEMO_SCRIPT.md`, `docs/REPORT_OUTLINE.md` (remove the visa material, add the substitute finder to the solution design), `docs/METRICS.md` (add "sessions resolved by substitute vs rescheduled"), `grounding/campus_ops_policy.md` (remove the visa and escalation rules, keep the attendance-threshold assumption labelled as **VERIFY**, and add the substitute rules: same module, free, daily load cap).
