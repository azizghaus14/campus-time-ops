# Campus Time Ops

**AI agents that re-plan APU's live timetable, with a human approving every step.**
APU Cloud Innovation Hackathon 2026, Category 02: Intelligent Automation & Digital Transformation.

> *We didn't build a chatbot. We built the layer that lets AI agents actually run university operations, on APU's live timetable, APU's real holidays and APU's own regulations, with a human approving every step.*

APSpace *shows* timetables. Campus Time Ops *re-plans and acts on* them:

- **Replan (hero).** A lecturer is sick, a room floods, or a public holiday is declared. The agent finds every affected class and tries a **substitute lecturer** first: someone who teaches the same module, is free, and is within their daily load, so no student is affected. It reschedules the rest with an **OR-Tools CP-SAT** solver, cites the APU rule behind every constraint, and waits for approval. It then creates **Google Calendar** events, **Gmail drafts** and a **change-log Doc** entry.
- **Slot Finder.** Finds slots where student groups, 2–3 examiners and a suitable room are all free (vivas, presentations, make-up classes, events), then drafts the invites.
- **Insights.** A Rooms heatmap, Timetable Health, and **Attendance Risk** ("you can miss at most 2 more classes", calculated from the real remaining sessions; read-only).

## What it looks like
- **Sign in as a persona:** Timetabling Office, Lecturer or Student. Each gets its own home and menu, and the API enforces the permissions.
- **Assistant home:** type what happened ("I'm sick tomorrow", "Room B-04-03 is flooded until Friday", "Monday 16 Nov is a public holiday"). The assistant shows the impact and a visual before/after plan, with **Approve**, **Prefer afternoon** and **No substitute** buttons. Nothing changes until someone approves.
- **3D campus:** a schematic model generated from APU room codes. Every room glows by its live state (in use, free, affected, moved here). It has day and week heat maps, a time scrubber, exploded floors and computed insights.
- **Lecturer "My week" and student "My timetable":** a visual calendar with changes highlighted. Students also get an attendance ring showing how many more classes they can miss.

## Quick start (offline, about 2 minutes)
```bash
make setup
```
```bash
make dev
```
The app runs on http://localhost:3000, and the API and MCP server on http://localhost:8000 (`/docs`, `/mcp`). Sign in as **Lecturer MZD** and click **"I'm sick tomorrow, sort out my classes"**, then **Approve & apply**. Then sign in as **Timetabling Office**, say "Monday 16 Nov is now a public holiday", and open **Campus** on Mon 16 Nov.

| Command | What it does |
|---|---|
| `make data` | Fetches the public APU feed, pseudonymises it, writes a dated snapshot, then generates the mocks and the synthetic students |
| `make data-offline` | Regenerates the mocks and synthetic data from the committed snapshot only |
| `make test` | Runs the 63 backend tests, including the solver property tests and the approval-gate tests |
| `make mcp` / `make inspector` | Runs the MCP server alone on :8001/mcp, or opens it in MCP Inspector |
| `make bench` | Re-measures the metrics in `docs/METRICS.md` |
| `make reset-demo` | Restores a clean demo state in under 10 s |
| `make deploy` | Deploys the backend and dashboard to Cloud Run (asia-southeast1). See `docs/SETUP_GOOGLE.md` |

If port 3000 is taken, run `PORT=3100 make frontend`. Configuration lives in `.env` (copy `.env.example`): `DATA_MODE=snapshot|live`, `DEMO_NOW`, `ATTENDANCE_THRESHOLD`, `NOTICE_HOURS`, `WORKSPACE_MODE=local|google`, and `MCP_AUTH_TOKEN`.

## Repository
```
backend/   FastAPI REST + FastMCP server (28 tools), CP-SAT solver, services, tests
frontend/  Next.js app: persona sign-in, assistant home, 3D campus (three.js), role-specific pages
agents/    Gemini Enterprise agent configs + instructions (replan, slot_finder) and ADK fallback (adk_app)
grounding/ APU handbook, holiday schedule, shuttle PDF, campus_ops_policy.md (rules labelled QUOTED / ASSUMPTION / VERIFY)
data/      pseudonymised snapshot, rooms, group sizes, holidays, shuttle, synthetic students
scripts/   fetch, generate, seed Firestore, reset, benchmark, deploy, scope check
docs/      ARCHITECTURE, DECISIONS, DEMO_SCRIPT, REPORT_OUTLINE, METRICS, SETUP_GOOGLE
```

## Measured results (`docs/METRICS.md`)
- **Whole-campus holiday:** 598 sessions solved by CP-SAT to OPTIMAL in about **2.5 s**. 94% stay physical, 5.6% go online and 0.5% are unresolved. **Zero clashes.**
- **Sick lecturer:** across the 10 busiest lecturers on one day, **67%** of sessions were covered by a substitute with no student affected, and the rest were rescheduled.
- **One approval** of a campus holiday produces 597 Calendar events, 378 Gmail drafts and one change-log entry.

## Data & privacy
- **A public feed only.** The timetable comes from APU's *public* feed (`open-ws/weektimetable`). We don't bypass any authenticated APU API. The holidays come from apu.edu.my, the shuttle times from the public PDF, and the rules from the APU Student Handbook.
- **Pseudonymised.** Staff names become deterministic pseudonyms (`Dr. Lecturer MDD`) and usernames are dropped before anything is written to disk. A test checks the committed snapshot.
- **Synthetic students.** All about 3,000 students are generated (`id, name, intake, grouping, attendance_records`), and their attendance is simulated against the real group timetable.
- **A human approves every step.** Action tools refuse any proposal that isn't `APPROVED` (tested). Approvals are recorded in an append-only audit log. The system **only creates Gmail drafts**, and a person sends them. Recipients are limited to the demo Workspace domain.
- **Least privilege.** The MCP endpoint requires a bearer token stored in Secret Manager and is rate-limited. The Cloud Run service account has only the Firestore, Secret accessor and Vertex AI user roles.
- **Running on real APSpace data with APU's permission.** Replace the loader with an authenticated APSpace or timetable API, keep the same service and MCP layer, add SSO (IAP or OAuth) in front of the MCP endpoint and the dashboard, and run a data-protection impact assessment with APU (contact: CTI).

## Status and open items
- **Agent platform:** per the organisers, the 13 Nov prototype does not need Gemini Enterprise. It ships with the in-app assistant plus the MCP server. For the 17 Nov final (Top 5), the Gemini Enterprise agents connect to the same MCP server through Google OAuth. The configs and instructions are ready in `agents/`, and the ADK + Vertex AI fallback also works (D-02).
- **Workspace actions:** the real Google Calendar, Gmail and Docs integration is implemented (`WORKSPACE_MODE=google`). It needs a demo Workspace account (see `docs/SETUP_GOOGLE.md`). Local mode writes real `.ics`, `.eml` and markdown files.
- **Still to do:** interviews (`TBD-interview` in METRICS), verifying the attendance threshold with APU, and the per-stop shuttle times (marked VERIFY).
