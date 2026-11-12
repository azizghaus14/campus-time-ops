# Campus Time Ops — Operational Policy Rules (prototype)

**Status:** authored for the APU Cloud Innovation Hackathon 2026 prototype.
Every rule has an ID that the agents and the solver cite. Each rule is labelled:

- **[QUOTED]**: taken from an APU document (source and section given). These are real APU rules.
- **[ASSUMPTION]**: a rule we chose for the prototype. It is plausible but not confirmed by APU. A human must confirm it before production use.
- **[VERIFY]**: the value must be confirmed with APU. It is configurable in `.env`.

Sources:
- *APU Student Handbook, Version 8.0, 1 July 2023* (`APU_Student_Handbook_Jul2023.pdf`), called **HB** below.
- *APU Holiday Schedule 2026*, https://apu.edu.my/node/501/, updated 12 Dec 2025 (`APU_Holiday_Schedule_2026.html`), called **HOL**.
- *APU Campus Connect shuttle schedule, V1_20261022, effective 22 Oct 2026* (`APU_Shuttle_Services_2026Oct22.pdf`), called **SHUTTLE**.

---

## 1. Attendance

### R-ATT-80: Minimum attendance per module [QUOTED]
> "All students must achieve a minimum of eighty percent (80%) attendance for each module, failing which the student may be denied assessment for that particular module." (HB §2.2, p.7)

Sessions include all tutor-led activities: lectures, seminars, tutorials and presentations. "Sessions" does not mean "weeks" (HB §2.2). Campus Time Ops therefore calculates attendance **per module**, and the module with the lowest attendance is the one that sets the limit.

### R-ATT-EXAM: Exam eligibility [QUOTED]
> "Students who do not fulfil the minimum attendance requirement of 80% will not be allowed to sit for the final examination." (HB §10.2, p.30)

### R-ATT-4C: Four consecutive absences [QUOTED]
If a student misses a module on **four consecutive occasions** in a semester, for a reason other than personal illness and without written approval, the student "may be deemed to have withdrawn from the module(s)" (HB §2.2, p.8). Attendance Risk flags 3 consecutive absences as an early warning.

### R-ATT-THRESHOLD: Attendance threshold used for forecasts [VERIFY]
Attendance Risk forecasts use `ATTENDANCE_THRESHOLD`, which defaults to **80%** to match R-ATT-80. This is the prototype's reading of the APU attendance rule, so the team must **verify** it with APU Academic Administration. Attendance Risk is a **read-only** view that covers all students. It never takes an action.

## 2. Timetable changes

### R-NOTICE-HB: Notice of changes [QUOTED]
APU commits to providing "appropriately staffed, programmed classes and as much notice as possible of any alterations to the published timetables." (HB §3.1, p.8)

### R-NOTICE: Minimum notice for a make-up class [ASSUMPTION]
A make-up class must start at least **24 hours** after the proposal is created (`NOTICE_HOURS`).
*Exception:* a change of room only, at the original date and time, needs no notice period, because the students' time commitment does not change.

### R-HOL: No classes on holidays [QUOTED]
No make-up classes on public holidays or on APU's additional holidays for students (HOL). "When a public holiday falls on a Sunday, the following day becomes a public holiday." (HOL). For 2026 this includes Deepavali on 7–9 Nov, Christmas on 24–25 Dec, and the Year End Break from 21 Dec 2026 to 2 Jan 2027. A holiday declared at short notice through a `HOLIDAY` disruption is treated in the same way once it has been executed.

### R-WEEKEND: No weekend make-up classes [ASSUMPTION]
Make-up classes are scheduled Monday to Friday. Saturday is allowed only when the planner explicitly sets `allow_saturday`.

### R-SHUTTLE: Classes end before the last shuttle [ASSUMPTION based on SHUTTLE facts]
SHUTTLE publishes **Monday–Friday** timetables only. The last *regular* departure from APU to LRT Bukit Jalil, the route that serves all students, is **19:15**. Trips at 20:45 and 21:45 are marked "Limited space only".
Rule: a **physical** make-up class must end at least **15 minutes** (`SHUTTLE_BUFFER_MIN`) before the last regular shuttle. On Monday to Friday that means it must end by 19:00. Online sessions are exempt. Set `SHUTTLE_INCLUDE_LIMITED=true` to count the limited-space trips.

### R-DURATION: Keep the duration [ASSUMPTION]
A moved session keeps its original duration.

### R-GRID: Prefer the standard slot grid [ASSUMPTION]
Prefer APU's standard 2-hour grid: 08:30, 10:45, 13:30, 15:45 and 18:45. These start times account for most sessions in the live feed. The session's original start time is also allowed.

## 3. Resources and clashes (hard constraints)

### R-CLASH-GROUP: No student-group clash [ASSUMPTION, obviously required]
An intake group `(INTAKE, GROUPING)` is never booked into two overlapping sessions.

### R-CLASH-LECT: No lecturer clash [ASSUMPTION, obviously required]
A lecturer is never booked into two overlapping sessions. A lecturer who is unavailable is blocked for the whole disruption window.

### R-ROOM-FREE: Room must be free [ASSUMPTION, obviously required]
A room is never double-booked. Rooms affected by a `ROOM_UNAVAILABLE` disruption are blocked for its window.

### R-ROOM-CAP: Capacity [ASSUMPTION; capacities are mocked]
The room's capacity must be at least the session's headcount. Room capacities and group sizes are **mock data**, because APU's room and staff feeds require authentication.

### R-ROOM-TYPE: Room type [ASSUMPTION]
Use the same type of room: a classroom moves to a classroom, a lab to a lab, an auditorium to an auditorium or a large classroom. A specialist room (studio, workshop, geology lab, iMac suite and so on) can only be replaced by **the same room**, because its equipment is specific to it.

## 3b. Substitute lecturers (first resort when a lecturer is unavailable)

### R-SUB-MODULE: A substitute must teach the same module [ASSUMPTION]
A substitute must already teach the **same module** somewhere in the live timetable. That means either the same module section (the same `MODID`), or the same module (the `MODID` without its section suffix, such as `CT044-3-1-IOOP` from `CT044-3-1-IOOP-L-8`, or the same module name). Ranking: same section first, then same module. Within those, lecturers from the same school rank higher, then lecturers with the lowest load that day.

### R-SUB-FREE: A substitute must be free [ASSUMPTION, obviously required]
The substitute must have no overlapping session for the whole slot. This includes other sessions they are covering in the same proposal.

### R-SUB-LOAD: Daily load cap [ASSUMPTION]
Covering a session must not take the substitute above **3 sessions on that day** (`SUB_MAX_DAILY_SESSIONS`).
A substitute keeps the session's original time and room, so **no student is affected**. If no substitute qualifies, or the approver declines the substitute, the session is rescheduled by the solver. The substitute is asked to confirm by a Gmail draft that a human sends.

## 4. Quality (soft objectives)

### R-LOAD: Student wellbeing [ASSUMPTION]
Avoid creating a day with more than 6 hours of class for any group, and avoid more than 3 sessions in a row.

### R-EVENING: Avoid evening slots [ASSUMPTION]
Prefer daytime. Physical evening make-up classes are already excluded by R-SHUTTLE.

### R-ONLINE: Online fallback [ASSUMPTION]
If no physical slot satisfies every hard rule, the session may be proposed **online** at a feasible time. This is shown explicitly, and the approver must accept it.

### R-UNRESOLVED: Report what cannot be placed [ASSUMPTION]
A session that cannot be placed is listed with its reason and the options: go online, extend the horizon, use a substitute lecturer, or cancel. It is never silently dropped.

## 5. Human in the loop

### R-HITL: A human approves every action [DESIGN RULE]
No agent sends an email, changes a calendar or writes the change log without a proposal in `APPROVED` status. The approval is recorded in the audit log. The system only ever creates Gmail **drafts**. A human reviews each draft and sends it from Gmail.
