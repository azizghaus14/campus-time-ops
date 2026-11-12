# BUILD PROMPT — "Campus Time Ops" (APU Cloud Innovation Hackathon 2026)

> Hand this whole document to a coding agent. It contains the context, the constraints, verified data facts, the architecture, every component spec, the build order and the acceptance criteria. Build exactly this; where something is marked **VERIFY**, check it before relying on it.

---

## 0. Your role and how to work

You are a senior full-stack + AI engineer building a hackathon project end to end on **Google Cloud**. Work in this repository. Build in the order given in §12, commit working increments, and keep everything runnable locally **and** deployable to Google Cloud.

Rules:
- **Polish beats breadth.** A flawless Replan agent (§7.1) matters more than three half-working agents. Never start a later milestone while an earlier one is broken.
- **A human approves every action.** No agent ever sends an email, changes a calendar or issues a warning without an explicit approve step in the UI or chat.
- **No real personal data in the demo.** The live timetable contains real staff names and usernames; pseudonymise them (§4.4). All student data is synthetic.
- **The demo must not depend on the network.** Snapshot all external data into the repo and default to the snapshot (§4.1).
- When the Google tooling (Gemini Enterprise, Anti-Gravity) behaves differently from what is described here, check the current official Google Cloud docs, pick the closest supported path, and note the deviation in `docs/DECISIONS.md`.

---

## 1. Hackathon context

- **Event:** APU Cloud Innovation Hackathon 2026, run by Asia Pacific University (APU, Kuala Lumpur, Malaysia) with NTT Data (Google Cloud Premium Partner) and GDG APU.
- **Category 02: Intelligent Automation & Digital Transformation.** The brief: AI-powered solutions that automate repetitive tasks and improve university workflows. The organisers' examples: HR & IT operations automation, a student performance chatbot for lecturers, and intelligent document processing.
- **Deliverables the team must submit:** (1) a 10-minute video demo of the solution and its technical implementation; (2) a detailed technical & project report covering the problem statement, development effort and timeline, solution design, and operational impact. You must also produce the material that feeds these (§13).
- **Provided stack:**
  - **Gemini Enterprise** (Google Cloud low/no-code agent platform):
    - data store connectors: 1P (Google Drive, Gmail, Calendar, Chat) and 3P (SharePoint, OneDrive, custom URIs, **MCP servers**)
    - ingestion and grounding of unstructured documents with citations
    - interactive chat agents
    - workflow agents (scheduled runs, e.g. a daily 9:00 AM sweep, with conditional approval)
    - actions (create Google Docs, draft emails, update data stores)
  - **Google Anti-Gravity:** an agentic IDE used to scaffold the application and UI and simplify deployment.

---

## 2. The product in one paragraph

**Campus Time Ops** is an AI operations layer on top of APU's **real, live timetable**. APU already has APSpace, which *displays* timetables and attendance; nothing *re-plans* or *acts* on them. Campus Time Ops adds agents that:
1. **Replan (hero feature).** Takes in a disruption (a lecturer is sick, a room is unavailable, a surprise public holiday), finds every affected class, computes clash-free make-up slots and rooms with a constraint solver, gets human approval, then updates Google Calendar, drafts the Gmail announcements and logs the change in a Google Doc.
2. **Slot Finder.** Finds slots where a student group, 2–3 examiners and a suitable room are all free, for vivas, presentations, make-up classes and events, then sends invites.
3. **Visa Guardian.** For international students, forecasts attendance against the student-pass requirement and tells each student exactly how many more classes they can miss, using their intake's **real remaining sessions**. It then runs an escalation ladder that a human approves.

Every decision cites APU policy (grounded documents), and every action is approved by a human.

**Pitch line:** *"We didn't build a chatbot. We built the layer that lets AI agents actually run university operations, on APU's live timetable, APU's real holidays and APU's own regulations, with a human approving every step."*

---

## 3. Architecture

```
                         ┌──────────────────────────────────────────────┐
  Lecturer / Admin ─────►│  Gemini Enterprise                           │
  (chat, NL request)     │   • Replan agent       (chat + actions)      │
                         │   • Slot Finder agent  (chat + actions)      │
                         │   • Visa Guardian      (workflow agent, 9AM) │
                         │   • Grounding store: APU handbook/policies   │
                         └───────────────┬──────────────────────────────┘
                                         │ MCP (3P connector)
                         ┌───────────────▼──────────────────────────────┐
                         │  Campus MCP Server  (Python, Cloud Run)      │
                         │   tools: timetable / rooms / holidays /      │
                         │          shuttle / solver / attendance /     │
                         │          proposals / actions                 │
                         └──┬─────────────┬──────────────┬──────────────┘
                            │             │              │
               ┌────────────▼───┐  ┌──────▼───────┐  ┌───▼──────────────────┐
               │ Data layer     │  │ Solver       │  │ Workspace actions    │
               │ snapshot+live  │  │ OR-Tools     │  │ Calendar/Gmail/Docs  │
               │ timetable,     │  │ CP-SAT       │  │ (demo Workspace      │
               │ mocks, Firestore│ │              │  │  accounts only)      │
               └────────────────┘  └──────────────┘  └──────────────────────┘
                            ▲
               ┌────────────┴─────────────────────────────────────────────┐
               │  Ops Dashboard (Next.js, scaffolded in Anti-Gravity,     │
               │  Cloud Run / Firebase Hosting) — reads REST API of the   │
               │  same backend: disruptions, approval queue, solver       │
               │  results, room heatmap, visa risk, audit log             │
               └──────────────────────────────────────────────────────────┘
```

**Tech choices (use these unless blocked):**
- **Backend:** Python 3.12, **FastAPI** (REST for the dashboard) and the official **MCP Python SDK** (`mcp`, FastMCP) exposing the same functions as MCP tools over **streamable HTTP**. One codebase, two interfaces.
- **Solver:** **Google OR-Tools CP-SAT.**
- **State:** **Firestore** (proposals, approvals, audit log, synthetic students). Locally, use the Firestore emulator or a JSON-file fallback behind the same repository interface.
- **Data files:** Parquet/JSON in `data/`, loaded into memory at startup. The dataset is small, about 25k rows.
- **Frontend:** **Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + Recharts**, scaffolded with Anti-Gravity.
- **Hosting:** **Cloud Run** for the backend and frontend. Secrets go in **Secret Manager**. Use the `asia-southeast1` region.
- **Agents:** **Gemini Enterprise** agents connected to the MCP server through the 3P MCP connector. **Fallback (VERIFY first):** if Gemini Enterprise cannot call a custom MCP server in the team's tenant, implement the same agents with **Google ADK (Agent Development Kit) + Gemini** (latest Gemini Pro/Flash model available in Vertex AI), consuming the same MCP server, and register or embed them where possible (an Agent Engine or a chat panel in the dashboard). Record which path was used in `docs/DECISIONS.md`.
- **Workspace actions:** prefer Gemini Enterprise's native actions (draft Gmail, create Docs, Calendar). Where those aren't available from an agent flow, implement them as MCP tools that call the Google Calendar, Gmail and Docs APIs using OAuth on **demo Workspace accounts only** (never real APU accounts).

---

## 4. Data — verified facts (checked November 2026)

### 4.1 Live timetable feed (PUBLIC, no auth)
- **URL:** `https://s3-ap-southeast-1.amazonaws.com/open-ws/weektimetable`
- The response is **gzip-compressed JSON**. Use `curl --compressed`, or `requests`, which decompresses automatically.
- It is a **rolling window of about 3–4 weeks**, and its contents change over time. A recent pull had **25,002 rows**, 1,143 intakes, 3,573 class codes, 494 lecturers and 236 rooms. An earlier pull had 31,606 rows.
- **Each row is one class session for one intake.** One physical session (same lecturer, room and start time) can include **up to about 123 intakes** (combined lectures). Always group by `(LECTID, ROOM, TIME_FROM_ISO)` to get physical sessions.
- **Volume:** on a typical weekday there are about **300–600 physical sessions**, representing about **800–2,200 intake rows**. Saturday and Sunday are almost empty.
- **Row schema** (all fields are always populated):

```json
{
 "INTAKE": "AFCF2509BA",            // intake code (student cohort)
 "MODID": "MPU1242-PS-T-3",          // module section id
 "MODULE_NAME": "Personal Skills",
 "DAY": "MON",                       // MON..SUN
 "LOCATION": "APU CAMPUS",           // "APU CAMPUS" | "ONL"
 "ROOM": "D-07-13",                  // physical room or online room
 "LECTID": "MDD",                    // lecturer short id
 "NAME": "<REAL STAFF NAME>",        // PII → pseudonymise
 "SAMACCOUNTNAME": "<staff username>",// PII → drop
 "DATESTAMP": "26-Oct-26",
 "DATESTAMP_ISO": "2026-10-26",
 "TIME_FROM": "03:45 PM", "TIME_TO": "05:45 PM",
 "TIME_FROM_ISO": "2026-10-26T15:45:00+08:00",
 "TIME_TO_ISO": "2026-10-26T17:45:00+08:00",
 "GROUPING": "G1",                   // G1..G6 tutorial/lab group within intake
 "CLASS_CODE": "SOF___MPU1242-PS-T-3___2026-10-05",
 "COLOR": "yellow"
}
```

- **The standard 2-hour slot grid** (these dominate the data): `08:30–10:30`, `10:45–12:45`, `13:30–15:30`, `15:45–17:45`, `18:45–20:45`. Other start times exist (09:00, 11:15, 14:30, 14:45, …). The solver should propose standard-grid slots by default and must check clashes against **any** overlapping time.
- **Room types**, inferred from the name:

| Room name | Type |
|---|---|
| `B-*`, `D-*`, `E-*`, `A-*`, `C-*`, `S-*` | Classrooms, coded block-floor-room |
| `Auditorium N @ …` | Auditoriums |
| `Tech Lab …` | Labs |
| `B-01-GEOLOGY LAB`, `B-03-Robotic LAB`, … | Specialist labs |
| `Discussion …` | Discussion rooms |
| `Culinary …` | Culinary rooms |
| `Presentation …` | Presentation rooms |
| `ONLMCO3-*`, `ONLINE*` | **Online** rooms, the busiest "rooms" in the data, meaning online delivery is common |

- **Snapshot:** `scripts/fetch_timetable.py` downloads the feed, pseudonymises it (§4.4) and writes `data/snapshots/timetable_<YYYY-MM-DD>.json` along with `data/snapshots/LATEST`. The app reads the snapshot by default. `DATA_MODE=live` re-fetches at startup and falls back to the snapshot on any error. **Commit one pseudonymised snapshot** so the demo is reproducible.
- Strip stray non-printable characters from room names (one room name contains a trailing junk byte).

### 4.2 Intake listing (PUBLIC)
- `https://s3-ap-southeast-1.amazonaws.com/open-ws/intake_listing`: gzip JSON with about 2,000 entries and fields like `INTAKE_CODE` and `COLOR` (some `INTAKE_CODE` values are null; filter them out). Snapshot it the same way.

### 4.3 Blocked sources → mock them
Exams, holidays, staff, bus, announcements and rooms feeds under `open-ws/*` and `api.apiit.edu.my/*` return **403/401**. Do not try to bypass authentication. Use these instead:
- **Public holidays:** the APU 2026 holiday schedule page `https://apu.edu.my/node/501/`. Scrape it once, or transcribe it by hand into `data/holidays_2026.json` (`[{date, name, type}]`). **VERIFY** the dates against the page.
- **Shuttle bus:** the public PDFs `https://publicwebsite-media.apu.edu.my/assets/2025-03/APU-SHUTTLE-SERVICES-WEF-20250403.pdf` (latest found) and `https://apu.edu.my/sites/default/files/apu-shuttle-services-wef-20241223.pdf`. Extract the **last departure from campus to each accommodation stop, per weekday**, into `data/shuttle.json`. If the PDF can't be parsed, transcribe it by hand. **VERIFY** whether a newer PDF exists on apu.edu.my.
- **Room capacities (mock):** `data/rooms.json`, generated from the 236 room names. Use these heuristics: auditorium 250–400, classroom 40–80, Tech Lab 30–45, specialist lab 20–30, discussion 8–12, online = unlimited. Seed with a fixed random seed so the numbers are stable.
- **Group sizes (mock):** students per `(INTAKE, GROUPING)` = a seeded random number from 15–60.
- **Exams (mock, only if Slot Finder needs it):** `data/exams_mock.json`.

### 4.4 Privacy / pseudonymisation (mandatory)
- Replace `NAME` with a deterministic fake name based on `LECTID`, for example `Dr. Lecturer MDD` or a seeded faker name. **Drop `SAMACCOUNTNAME`.**
- Keep `LECTID`, since it is a short code and needed for joins.
- Every student is synthetic.
- Add a "Data & Privacy" section to the README and the report: public feed, pseudonymised, synthetic students, human approval for every step, least-privilege access, and how this would run against real APSpace data with APU's permission.

### 4.5 Grounding documents (for Gemini citations)
Download into `grounding/` and ingest into the Gemini Enterprise data store (or a Vertex AI Search data store for the ADK path):
- APU Student Handbook (Jul 2023): `https://apiit.atlassian.net/wiki/download/attachments/1199570953/APU%20Student%20Handbook-Jul%202023.pdf?api=v2`. **VERIFY** whether a newer version exists on the APU knowledge base (`https://apiit.atlassian.net/wiki/`).
- The APU 2026 holiday schedule page (saved as PDF/HTML).
- The shuttle bus PDF.
- **Policy rules file (authored, clearly labelled):** `grounding/campus_ops_policy.md`. It defines the operational rules the agents enforce: make-up class rules, the minimum notice period, no make-up classes on public holidays, and evening classes ending before the last shuttle. It also covers the attendance threshold for international students (**default 80%, VERIFY against EMGS / APU International Office and make it configurable**) and the escalation ladder. Label clearly which rules are quoted from APU documents and which are assumptions used in the prototype.

---

## 5. Core domain model (`backend/app/domain.py`)

```python
Session        # one physical session: id, class_codes[], module_id, module_name,
               # lecturer_id, room, start, end, intakes: [(intake, grouping)], location
Disruption     # id, type: LECTURER_UNAVAILABLE | ROOM_UNAVAILABLE | HOLIDAY,
               # scope (lecturer_id | rooms[] | date), window (start,end), reason, created_by
Proposal       # id, disruption_id, moves: [Move], unresolved: [Session+reason],
               # score, status: DRAFT|APPROVED|REJECTED|EXECUTED, citations[]
Move           # session_id, from(start,end,room) -> to(start,end,room|ONLINE),
               # affected_groups, rationale (human-readable, cites rule ids)
Student        # synthetic: id, name, intake, grouping, nationality, is_international,
               # pass_expiry, passport_expiry, attendance_records[]
AuditEvent     # who, what, when, before/after, proposal_id
```

A **student group** is `(INTAKE, GROUPING)`. Students in an intake follow the same group timetable, so group-level clash checking represents the real constraint.

---

## 6. Campus MCP Server — tool contracts

Implement each tool as a plain Python function in `backend/app/services/` and expose it **both** as an MCP tool (`backend/app/mcp_server.py`) and as a FastAPI route (`backend/app/api.py`). Inputs and outputs are JSON. Every tool must:
- validate its inputs
- return structured errors
- never perform a side effect (sending, writing to a calendar, issuing a warning) unless given a `proposal_id` that is in `APPROVED` status

**Read tools**
- `get_lecturer_schedule(lecturer_id, start_date, end_date)` → physical sessions.
- `get_group_schedule(intake, grouping, start_date, end_date)`.
- `get_room_schedule(room, date)`, `find_free_rooms(start, end, min_capacity, room_type?)`.
- `get_sessions_on(date, filters?)`: sessions for a date, with optional filters.
- `search_lecturers(query)`, `search_intakes(query)`: fuzzy search over the pseudonymised data.
- `get_holidays(year)`, `get_last_shuttle(date)`.
- `get_room_utilisation(date_range)`: utilisation per room per hour, for the heatmap and energy features.
- `timetable_health(date_range)`: long gaps, more than 3 back-to-back sessions, days over 6 hours, lecturer load.

**Planning tools**
- `create_disruption(type, scope, window, reason)` → a disruption with its list of affected sessions.
- `plan_replan(disruption_id, options)` → runs the solver and returns a `DRAFT` proposal with rationale and citations. `options`: search horizon (default the next 10 working days), allow online fallback (true), preferred slots, max moves per group per week.
- `find_common_slots(groups[], lecturer_ids[], duration_min, window, room_requirements)` → ranked candidate slots (Slot Finder).
- `explain_proposal(proposal_id)` → a plain-language summary for the agent to show.

**Approval & action tools** (each requires an approved proposal)
- `approve_proposal(proposal_id, approver, edits?)`, `reject_proposal(proposal_id, reason)`.
- `execute_proposal(proposal_id)` → creates or updates the Google Calendar events for the demo accounts, creates **Gmail drafts** (not sends) for each affected group and the lecturer, appends to a Google Doc "Timetable Change Log", writes `AuditEvent`s, and sets the status to `EXECUTED`.
- `send_drafts(proposal_id)`: optional, requires a second explicit confirmation, demo accounts only.

**Visa tools**
- `get_attendance(student_id)`, `attendance_forecast(student_id)` → current %, trend, projected % at the end of term, the **remaining sessions for the student's group (from the real timetable)**, `max_more_absences`, and the projected date of breaching the threshold.
- `visa_risk_sweep(date)` → a ranked list of at-risk international students, each with a proposed escalation step.
- `parse_passport_image(image)` → extracts the passport's machine-readable lines (MRZ) using Gemini multimodal, validates the **MRZ check digits** with the ICAO 9303 algorithm, and returns structured fields plus any mismatches against the student record.
- `plan_escalation(student_id)` → a `DRAFT` proposal: nudge email → advisor meeting (Calendar slot found via `find_common_slots`) → formal warning letter (Google Doc from a template) → International Office approval.

---

## 7. Agent specifications

Write each agent's system instructions in `agents/<name>/instructions.md` and its configuration (tools, data stores, schedule) in `agents/<name>/config.yaml`. Paste or deploy them into Gemini Enterprise, or load them in the ADK fallback.

### 7.1 Replan agent (HERO — build first, polish most)
**Users:** lecturers, programme leaders, the timetabling office.
**Triggers (natural language):**
- "I'm sick tomorrow, sort out my classes" (the lecturer is identified by the logged-in demo user or asked for)
- "Room B-04-03 is flooded until Friday"
- "The government just declared Monday 16 Nov a public holiday"

**Flow:**
1. Work out the disruption type, scope and time window. Ask **at most one** clarifying question, and only if it's ambiguous.
2. `create_disruption` → state the impact: *"This affects 4 sessions, 9 intake groups and ~310 students."*
3. `plan_replan` → present the proposal as a compact table: session → new slot and room, groups, and the rule cited. List any unresolved sessions with reasons and options (go online, extend the horizon, cancel).
4. Ask for approval. Allow edits ("move the Thursday one to the afternoon") → re-plan.
5. On approval: `approve_proposal` → `execute_proposal` → report what was done, with links to the Calendar events, Gmail drafts and change-log Doc.

**Behaviour rules:**
- Never take an action before approval.
- Always cite the policy rules (grounded) behind a constraint.
- Always state the counts.
- Keep answers short.

**Bulk holiday mode:** for a `HOLIDAY` disruption covering the whole campus (~300–600 physical sessions), the agent summarises by faculty and day rather than listing every move. The dashboard shows the full list.

### 7.2 Slot Finder agent
**Requests:**
- "Schedule FYP vivas for intake APD3F2505CS: each needs the supervisor, the second marker and a presentation room, 45 minutes, next week."
- "Find a 2-hour slot for a guest talk that intakes X, Y and Z can all attend."

**Flow:**
1. Get the students' and examiners' constraints.
2. Call `find_common_slots`.
3. Show the top 3 options with a reason for each.
4. On approval, create a proposal → Calendar invites and Gmail drafts.

### 7.3 Visa Guardian (workflow agent + chat)
- **Scheduled daily at 09:00 MYT:** `visa_risk_sweep` → for each at-risk student, run `plan_escalation` → post a digest to the International Office (Google Chat message or an email draft) containing the approval links.
- **Student-facing chat:** "How many more classes can I miss?" → *"You're at 83%. Your intake has 22 sessions left this term. If you miss more than 2, you'll fall below the 80% student-pass requirement. Your next class is Tue 10:45, D-07-13."* (Only for the student's own record.)
- **Passport check:** upload an image → `parse_passport_image` → flag expiry before the pass expiry date, and flag name or number mismatches.
- Every escalation step needs International Office approval. Use wording that supports the student, not punishes them.

### 7.4 (Optional) Ops Q&A
A grounded chat agent over the timetable tools and the policies. For example: "Which intakes have more than 6 hours of class on Fridays?" or "Which rooms are empty after 3 PM on Wednesdays?"

---

## 8. Solver specification (`backend/app/solver/`)

Use **OR-Tools CP-SAT**. Discretise time into **15-minute ticks** between 08:30 and 21:00 MYT, and consider only working days that aren't holidays.

**Inputs:**
- the sessions to move
- the horizon of candidate days
- all existing sessions (minus the ones being moved)
- rooms with capacity and type
- group sizes
- holidays
- the last shuttle per day
- the options from `plan_replan`

**Decision variables:** for each session to move, a candidate `(day, start_tick, room)`, plus a boolean "online fallback" or "unresolved".

**Hard constraints:**
1. **No group clash:** for every `(intake, grouping)` in the session, nothing overlaps with that group's other sessions, including other sessions being moved.
2. **No lecturer clash:** the lecturer (or the substitute, if one is given) is free. A `LECTURER_UNAVAILABLE` disruption blocks that lecturer for the whole window.
3. **Room is free and big enough:** capacity ≥ the sum of group sizes, and the room type matches the original (lab → lab). Rooms in a `ROOM_UNAVAILABLE` disruption are blocked.
4. **Not on a holiday or a weekend** (unless the option allows Saturday).
5. **Keep the duration** of the original session.
6. **Shuttle rule:** the session ends at least 15 minutes before the last shuttle that day.
7. **Notice period:** the new slot is at least 24 hours after the proposal is created (configurable).

**Soft objectives (weighted sum, minimised):**
- Prefer the same room, then the same block, then any room.
- Prefer standard grid slots.
- Prefer sooner dates (closest to the original).
- Avoid creating more than 3 consecutive sessions, or a day over 6 hours, for any group.
- Avoid evening slots.
- Penalise online fallback heavily, and penalise leaving a session unresolved most heavily.

**Outputs:** moves with a per-move rationale (which constraints were binding), a list of unresolved sessions, solve-time statistics and the objective value. Use a 10-second time limit for bulk holiday solves and 3 seconds for small ones.

**Performance:** for a whole-campus holiday, solve it as one model if it finishes within 10 s. Otherwise split it by building or faculty into sub-problems and solve them in order, each respecting earlier assignments. Pre-compute free-interval indexes per room, group and lecturer so the model stays small (only feasible candidates become variables).

**Tests (`backend/tests/test_solver.py`):**
- no clash is ever produced (property test over random disruptions)
- capacity is respected
- holidays are excluded
- the shuttle rule holds
- determinism with a fixed seed

---

## 9. Synthetic data generator (`scripts/generate_synthetic.py`)

- **Students:** about 3,000 synthetic students spread across about 150 real intakes from the snapshot, 30–40% international. Use a seeded random generator and never real names.
- **Attendance:** generate `attendance_records` for past sessions of each student's real group timetable. Mix a few profiles: steady 95%, slowly declining, sudden drop, at-risk (78–84%). Guarantee **at least 6 compelling demo students**, including the one used in the demo script (§13.2).
- **Pass and passport expiries:** spread across the next 1–18 months. Include 2 cases where the passport expires before the pass.
- **Passport images:** generate 3–4 sample passport images with valid ICAO MRZ lines and clearly fictional data ("SPECIMEN" watermark), plus 1 with a wrong check digit. Store them in `data/demo_passports/`.

---

## 10. Ops Dashboard (`frontend/`, scaffolded with Anti-Gravity)

Clean, modern, demo-friendly, light and dark mode, MYT time zone everywhere.

**Pages:**
1. **Overview:** today's sessions, active disruptions, pending approvals, students at visa risk, KPI tiles (hours saved, sessions re-planned, median time to re-plan).
2. **Disruptions:** create a disruption (form) or watch ones created by the agents. Shows the **live re-plan animation**: affected sessions appear red on a week grid (rows = rooms or groups, columns = days and slots), the solver runs, and sessions turn green as they're placed. This is the visual for the demo's main moment.
3. **Proposal detail:** a table of moves (before → after, groups, room, rationale, cited rule), a list of unresolved sessions, an **Approve / Edit / Reject** panel, and after execution, links to the Calendar events, Gmail drafts and change-log Doc.
4. **Slot Finder:** pick groups and examiners → ranked slots on a calendar view.
5. **Visa Guardian:** a risk table (attendance, trend line, max more absences, pass expiry), a student drill-down with a forecast chart, the escalation ladder state, and a passport upload check.
6. **Rooms & Energy:** a room utilisation heatmap (room × hour) and the "empty rooms right now" list, with an estimated energy saving (assume a configurable kWh per empty air-conditioned room-hour and an RM per kWh tariff, both clearly labelled as assumptions).
7. **Timetable Health:** charts for long gaps, overloaded days and lecturer load.
8. **Audit log:** every proposal, approval and action.

The frontend talks only to the FastAPI REST API. Add an embedded chat panel only in the ADK fallback path (§3). Otherwise agents are used inside Gemini Enterprise and the dashboard reflects their proposals through Firestore.

---

## 11. Repository layout

```
/backend
  app/{main.py, api.py, mcp_server.py, domain.py, config.py}
  app/data/{loader.py, pseudonymise.py, indexes.py}
  app/services/{timetable.py, rooms.py, holidays.py, shuttle.py, replan.py,
                slots.py, visa.py, mrz.py, workspace.py, audit.py, store.py}
  app/solver/{model.py, objectives.py, decompose.py}
  tests/
  Dockerfile, pyproject.toml
/frontend            (Next.js, Anti-Gravity scaffold)
/agents/{replan,slot_finder,visa_guardian,ops_qa}/{instructions.md, config.yaml}
/grounding/          (PDFs + campus_ops_policy.md)
/data/{snapshots/, rooms.json, holidays_2026.json, shuttle.json, demo_passports/}
/scripts/{fetch_timetable.py, generate_synthetic.py, seed_firestore.py,
          reset_demo.py, deploy.sh}
/docs/{ARCHITECTURE.md, DECISIONS.md, DEMO_SCRIPT.md, REPORT_OUTLINE.md,
       METRICS.md, SETUP_GOOGLE.md}
README.md, Makefile, .env.example
```

**Makefile targets:** `make data` (fetch + pseudonymise + synthetic), `make dev` (backend + frontend + Firestore emulator), `make test`, `make mcp` (run the MCP server locally), `make deploy`, `make reset-demo` (restore a clean demo state in under 10 seconds).

**`.env.example`:** `GCP_PROJECT`, `REGION=asia-southeast1`, `DATA_MODE=snapshot|live`, `ATTENDANCE_THRESHOLD=0.80`, `NOTICE_HOURS=24`, `GEMINI_MODEL`, `WORKSPACE_DEMO_DOMAIN`, OAuth client IDs (via Secret Manager in the cloud), `MCP_AUTH_TOKEN`.

**MCP security:** require a bearer token (or IAP / OAuth if Gemini Enterprise supports it, **VERIFY**). Rate-limit requests. Make action tools refuse anything without an approved proposal.

---

## 12. Build order and milestones

1. **M0 — Skeleton (½ day):** repo layout, Makefile, `.env.example`, CI that runs the tests, `docs/DECISIONS.md` started.
2. **M1 — Data (½ day):** fetch, pseudonymise, snapshot; loader and indexes (by lecturer, group, room, date, physical session); rooms, holidays and shuttle files. Unit tests: the row counts and physical-session grouping match §4.1.
3. **M2 — Read tools + REST + MCP (1 day):** all read tools. Run the MCP server locally and test it with the MCP Inspector.
4. **M3 — Solver + Replan planning (1.5 days):** CP-SAT model, the three disruption types, rationale, tests. Benchmarks: a sick lecturer in under 3 s, a campus-wide holiday in under 10 s (with decomposition if needed).
5. **M4 — Approvals + Workspace actions (1 day):** the proposal lifecycle, Firestore, Calendar events, Gmail drafts, the change-log Doc, the audit log.
6. **M5 — Replan agent in Gemini Enterprise (1 day):** connect the MCP server (or the ADK fallback), ingest the grounding docs, write the instructions, and run the three demo prompts end to end.
7. **M6 — Dashboard core (1.5 days):** Overview, Disruptions with the live re-plan animation, Proposal detail with approve, Audit.
   - **⇒ At this point the hero demo must work end to end. Freeze it, then tag `v1-hero`.**
8. **M7 — Slot Finder (½–1 day):** reuse the solver; the agent; the dashboard page.
9. **M8 — Visa Guardian (1.5 days):** synthetic students, forecast, MRZ parser and validator, escalation proposals, the 09:00 workflow, the dashboard page.
10. **M9 — Insights (½ day):** Rooms & Energy, Timetable Health.
11. **M10 — Deploy + hardening (1 day):** Cloud Run, Secret Manager, auth, `reset-demo`, error states, loading states, the offline snapshot path, tested on a fresh project using `docs/SETUP_GOOGLE.md`.
12. **M11 — Demo + report material (1 day):** §13.

If time runs short, cut in this order: M9 → the passport part of M8 → the rest of M8 → M7. **Never cut M1–M6.**

---

## 13. Demo and report material

### 13.1 Metrics (`docs/METRICS.md`)
Measure them from the system, not invented. Use these:
- solver time per disruption type
- sessions, groups and students affected
- the share of sessions placed in a physical room versus online versus left unresolved
- the number of actions automated per disruption (calendar events, drafts, log entries)
- the estimated staff time saved (a baseline from team interviews; a placeholder clearly marked `TBD-interview` until then)

### 13.2 `docs/DEMO_SCRIPT.md`: the 10-minute video
| Time | Segment |
|---|---|
| 0:00–1:00 | **Problem.** APU timetable numbers from the snapshot; how disruptions are handled today (interview quote placeholder). APSpace shows timetables but doesn't re-plan them. |
| 1:00–2:00 | **Architecture.** The diagram; real data, real rules, real engineering, human approval. |
| 2:00–4:00 | **Replan, small.** "I'm sick tomorrow" → impact → proposal with citations → edit → approve → Calendar, Gmail drafts and change log appear live. |
| 4:00–5:30 | **Replan, wow.** "Monday is now a public holiday" → the dashboard grid turns red (~600 sessions) → the solver turns it green → summary by faculty, the online fallback for leftovers, the shuttle rule enforced. |
| 5:30–6:30 | **Slot Finder.** Viva scheduling with 3 examiners → ranked slots → invites. |
| 6:30–8:00 | **Visa Guardian.** The 9 AM sweep → at-risk digest → a student asks "how many classes can I miss?" (real remaining sessions) → passport upload catches an expiry mismatch → escalation approved. |
| 8:00–9:00 | **Insights.** Room heatmap and energy saving, timetable health. |
| 9:00–10:00 | **Impact and scale.** Metrics, privacy and human-in-the-loop, roadmap (APSpace integration, other universities, enterprise shift planning). |

### 13.3 `docs/REPORT_OUTLINE.md`
Sections:
- **Problem statement:** with data from the snapshot and interview quotes.
- **Stakeholders.**
- **Solution design:** architecture, MCP tools, solver formulation, agents, grounding.
- **Development timeline:** generated from the milestones and git history.
- **Testing.**
- **Operational impact:** metrics from §13.1.
- **Privacy, ethics and responsible AI.**
- **Limitations:** mocked data, verified versus assumed rules.
- **Future work.**
- **Appendix:** tool list, data dictionary.

---

## 14. Acceptance criteria (definition of done)

- [ ] `make data && make dev` works on a clean machine. `make test` passes, including the solver property tests.
- [ ] The demo runs fully from the committed snapshot with no internet access to APU.
- [ ] No real staff names or usernames appear anywhere in the UI, logs, docs or video assets.
- [ ] The three Replan prompts in §7.1 work end to end in the chosen agent platform, with citations and an approval step, and produce real Calendar events, Gmail **drafts** and a change-log Doc on the demo Workspace.
- [ ] No action tool works without an approved proposal (tested).
- [ ] The whole-campus holiday re-plan finishes in under 10 s and animates on the dashboard.
- [ ] Every solver output has zero group, lecturer or room clashes (an automated check runs after every solve).
- [ ] Visa Guardian's "max more absences" equals a hand calculation for 3 test students.
- [ ] The MRZ validator accepts the valid specimens and rejects the bad check digit.
- [ ] It's deployed on Cloud Run with secrets in Secret Manager, and `make reset-demo` restores a clean state.
- [ ] `docs/` contains ARCHITECTURE, DECISIONS (including the Gemini Enterprise vs ADK path), DEMO_SCRIPT, REPORT_OUTLINE, METRICS and SETUP_GOOGLE.

---

## 15. Open items the human team must handle (don't block on them, use placeholders)

1. **Interview 1–2 APU lecturers or programme admins:** how rescheduling, viva scheduling and attendance warnings work today, and how long they take. Put the quotes into `docs/METRICS.md` and the report.
2. **Confirm with APU's International Office or EMGS:** the student-pass attendance threshold and the renewal timelines. Update `ATTENDANCE_THRESHOLD` and `campus_ops_policy.md`.
3. **Optionally ask APU (CTI, cti@apu.edu.my) for permission** to use the public timetable feed. It strengthens the pitch.
4. **Set up the hackathon GCP project, Gemini Enterprise access and demo Workspace accounts** (lecturer, programme leader, International Office, 2–3 students).
