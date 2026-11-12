# Technical & project report: outline

## 1. Problem statement
- **APU's timetable at scale** (snapshot of 12 Nov 2026): 25,002 intake-session rows, 7,656 physical sessions in a 3-week window, 1,143 intakes, 494 lecturers and 235 rooms. A busy weekday has about 600 physical sessions. Combined lectures reach up to 123 intakes, and online delivery is common.
- **Disruptions today:** sick lecturers, closed rooms and short-notice public holidays are handled by hand, by phone and email. Interview quotes go here: `TBD-interview`.
- **The gap:** APSpace *displays* timetables and attendance, but nothing *re-plans* them or *acts* on them.

## 2. Stakeholders
Lecturers, programme leaders, the timetabling office, students, and Academic Administration (attendance). There are also CTI (data owner and permission) and IT (Workspace and Google Cloud).

## 3. Solution design
- **Architecture:** `docs/ARCHITECTURE.md`. One FastAPI process exposes REST for the dashboard and MCP for the agents, on Cloud Run. State lives in Firestore and secrets in Secret Manager.
- **MCP tools:** 28 tools. See the appendix.
- **Substitute finder (A1):** a substitute must teach the same module section or module, be free, and stay within 3 sessions that day. Ranking: section > module, then same school, then lowest load. It is tried first for an unavailable lecturer, so the time and room stay the same and no student is affected.
- **Solver formulation (CP-SAT):** see the docstring in `backend/app/solver/model.py` and DECISIONS D-10.
  - *Decision variables:* one boolean per pre-filtered candidate, plus an "unresolved" variable per session.
  - *Hard constraints:* no group, lecturer or room clashes, capacity, room type, no holidays or weekends, kept duration, the shuttle rule and the notice period.
  - *Soft objectives:* same room or block, the standard grid, sooner dates, the R-LOAD limits, avoiding evenings, with online and unresolved penalised.
  - *Engineering:* a greedy warm start, decomposition by school, and an independent clash checker.
- **Agents:** Replan (the hero, which also answers attendance questions) and Slot Finder, in Gemini Enterprise with the 3P MCP connector, plus the ADK fallback.
- **Grounding:** the APU Student Handbook (§2.2 attendance, §3.1 notice, §10.2 exam eligibility), the APU 2026 holiday schedule, the 22 Oct 2026 shuttle PDF, and `campus_ops_policy.md`, whose rules are labelled QUOTED / ASSUMPTION / VERIFY.
- **Dashboard:** 8 pages, with screenshots.

## 4. Development effort and timeline
Generate the milestone list from `git log --reverse --format='%ad %s' --date=short`:
- M0–M4: backend, data, solver, approvals
- Scope trim v2: removed the out-of-scope features and added the substitute finder
- M6: dashboard
- Agents, docs and deployment

`v1-hero` tags the frozen hero demo.

## 5. Testing
There are 50 automated tests (`make test`):
- **Data:** row counts, physical-session grouping, no personal data, clean room names
- **Solver:** a Hypothesis property test over random disruptions (no clashes, capacity, holidays, shuttle rule, notice period, kept duration), a planted-clash detector, determinism, the holiday solving in under 10 s, the decomposition path, and edit pins
- **Substitutes:** every substitute is free and genuinely teaches the module; ranking; the demo lecturer case
- **Approval gate:** every action is refused without APPROVED, including DRAFT, REJECTED and SUPERSEDED proposals; no send capability exists; edits that would create a clash are refused
- **Attendance:** matches a hand calculation for 3 students
- **API and MCP:** auth and tool listing

Manual checks: an end-to-end run in the dashboard, the MCP client, and ADK tool discovery.

## 6. Operational impact
Use `docs/METRICS.md`: solve times, the physical / online / unresolved shares, substitutes vs rescheduled, the actions automated per disruption, and staff-hours saved once the interview baseline (`TBD-interview`) is filled in.

## 7. Privacy, ethics and responsible AI
- The data comes from a public feed. Staff names are pseudonymised and usernames dropped. Every student is synthetic.
- A human approves every action, and approvals are recorded in an append-only audit log. The system creates email drafts only. Recipients are restricted to the demo domain.
- Access is least-privilege: a bearer-protected MCP endpoint, Secret Manager, and a minimal set of service-account roles.
- The attendance view is read-only, uses supportive wording, and takes no automated action.
- **Running on real APSpace data, with APU's permission:**
  - swap the loader for an authenticated APSpace or timetable API
  - keep pseudonymisation for analytics
  - require SSO through IAP or OAuth on the MCP endpoint and the dashboard
  - run a DPIA with APU

## 8. Limitations
- Room capacities and group sizes are mocked. The shuttle per-stop times are transcribed (VERIFY). The 80% attendance threshold applies per module under HB §2.2; the forecast threshold still needs to be verified with APU.
- The feed covers a rolling window of about 3 weeks, so earlier and later weeks are projected from weekly patterns (D-09).
- Gemini Enterprise MCP support in the tenant still needs to be verified (D-02).
- The in-memory timetable overlay means the backend runs as a single instance.

## 9. Future work
APSpace integration, exam-period planning, preference learning (lecturer availability), other universities, and enterprise shift and room planning.

## Appendix
- **A. MCP tool list:** `search_lecturers`, `search_intakes`, `get_lecturer_schedule`, `get_group_schedule`, `get_room_schedule`, `get_sessions_on`, `find_free_rooms`, `get_holidays`, `get_last_shuttle`, `get_room_utilisation`, `empty_rooms_now`, `timetable_health`, `get_policy`, `create_disruption`, `find_substitutes`, `plan_replan`, `explain_proposal`, `get_proposal`, `list_proposals`, `find_common_slots`, `create_slot_proposal`, `approve_proposal`, `reject_proposal`, `execute_proposal`, `search_students`, `get_attendance`, `attendance_forecast`, `attendance_risk_list`.
- **B. Data dictionary:** the feed row schema (BUILD_PROMPT §4.1); Session, Disruption, Proposal, Move (type, from, to, rationale, rule_ids) and AuditEvent (`backend/app/domain.py`); `rooms.json`, `group_sizes.json`, `holidays_2026.json`, `shuttle.json`; `synthetic/students.json` (`id, name, intake, grouping, attendance_records`).
