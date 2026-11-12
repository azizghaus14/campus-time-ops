# Architecture

```
                         ┌───────────────────────────────────────────────┐
  Lecturer / Admin ─────►│  Gemini Enterprise  (or ADK fallback, D-02)   │
  (chat, natural lang.)  │   • Replan agent      (chat + actions)        │
                         │       substitutes → reschedule → approve      │
                         │       + "how many more classes can I miss?"   │
                         │   • Slot Finder agent (chat + actions)        │
                         │   • Grounding store: APU handbook, holidays,  │
                         │     shuttle PDF, campus_ops_policy.md         │
                         └───────────────┬───────────────────────────────┘
                                         │ MCP (3P connector, streamable HTTP, bearer)
                         ┌───────────────▼───────────────────────────────┐
                         │  Campus MCP Server + REST API (FastAPI, one   │
                         │  process on Cloud Run)  /mcp  and  /api        │
                         │   read: timetable · rooms · holidays · shuttle│
                         │   plan: disruptions · substitutes · solver ·  │
                         │         slots · proposals                     │
                         │   act:  approve → execute (APPROVED only)     │
                         │   attendance (read-only)                      │
                         └──┬─────────────┬──────────────┬───────────────┘
                            │             │              │
               ┌────────────▼───┐  ┌──────▼───────┐  ┌───▼───────────────────┐
               │ Data layer     │  │ Solver       │  │ Workspace actions     │
               │ pseudonymised  │  │ OR-Tools     │  │ Calendar · Gmail      │
               │ snapshot (live │  │ CP-SAT +     │  │ DRAFTS · Change-log   │
               │ optional),     │  │ substitute   │  │ Doc (demo accounts)   │
               │ busy indexes,  │  │ finder       │  │ or local outbox       │
               │ Firestore state│  │              │  │                       │
               └────────────────┘  └──────────────┘  └───────────────────────┘
                            ▲
               ┌────────────┴──────────────────────────────────────────────┐
               │  Ops Dashboard (Next.js on Cloud Run) → /api via a server- │
               │  side proxy (the token never reaches the browser):         │
               │  Overview · Disruptions (live re-plan grid) · Proposals    │
               │  (approve/edit/reject) · Slot Finder · Rooms · Timetable   │
               │  Health · Attendance Risk · Audit log                      │
               └────────────────────────────────────────────────────────────┘
```

## Request flow: "I'm sick tomorrow"
1. The agent calls `create_disruption(LECTURER_UNAVAILABLE, {lecturer_id}, window)`. The backend finds the lecturer's upcoming physical sessions in the window and computes the impact: sessions, intake groups and students.
2. The agent calls `plan_replan(disruption_id)`.
   1. **Substitutes first.** `find_substitutes` returns the lecturers who teach the same module section or module, are free for the slot, and stay within 3 sessions that day. They are ranked by same section, then same school, then lowest load. A per-proposal overlay prevents double-booking the same substitute.
   2. **Solver for the rest.** CP-SAT runs over pre-filtered candidates: working days in the horizon (no holidays or weekends), the 24-hour notice period, the shuttle rule, kept duration, a free lecturer and groups, and a free room of the right type and capacity. Constraints between moved sessions are `AtMostOne` per room, lecturer and group time point. The soft objectives are: the same room or block, the standard grid, sooner dates, the R-LOAD limits, avoiding evenings, and online or unresolved as a last resort.
   3. **Independent clash check.** It runs after the solve, and the proposal is stored as a `DRAFT` with a rationale for each move and the cited rule IDs.
3. The human reviews the proposal, in chat or on the dashboard, and can edit it: pins, a morning or afternoon preference, or declining a substitute. Each edit creates a re-plan and a new version.
4. The agent calls `approve_proposal(approver)` and then `execute_proposal`. Execution creates:
   - Calendar events (a lecturer change for a substitute, a new slot for a reschedule)
   - Gmail **drafts**: the substitute is asked to confirm, and lecturers and groups are notified
   - a change-log Doc entry
   - audit events

   It then updates the timetable overlay. Any status other than `APPROVED` gets `403 NOT_APPROVED`.

## Components
| Path | What |
|---|---|
| `backend/app/data/` | Loader (snapshot, or live with snapshot fallback), pseudonymisation, room catalogue and group sizes, busy-interval indexes |
| `backend/app/solver/` | `model.py` (candidates, CP-SAT, greedy, clash checker), `objectives.py` (weights), `decompose.py` (split by school) |
| `backend/app/services/` | `timetable`, `rooms`, `holidays`, `shuttle`, `replan`, `substitutes`, `slots`, `attendance`, `proposals` (lifecycle), `workspace` (Google and local), `audit`, `store` (Firestore and JSON), `policy` (the rule registry parsed from `grounding/campus_ops_policy.md`) |
| `backend/app/mcp_server.py` | 28 MCP tools. Each wraps a service function and returns structured `{"error": {...}}` on failure |
| `backend/app/api.py`, `main.py` | REST routes, bearer auth for `/mcp` (and for `/api` writes in the cloud), a rate limit, and the `/outbox` static files |
| `frontend/` | Next.js dashboard, with `app/api/backend/[...path]` as the token-adding proxy |
| `agents/` | Gemini Enterprise configs and instructions, and the ADK fallback |

## Security and privacy
- **MCP:** a bearer token (`MCP_AUTH_TOKEN`, stored in Secret Manager) and a rate limit of 120 requests per minute per client. Action tools refuse anything that isn't `APPROVED`.
- **No sending:** the system never sends email. Drafts are restricted to `WORKSPACE_DEMO_DOMAIN`.
- **Privacy:** staff names are pseudonymised (`Dr. Lecturer MDD`), `SAMACCOUNTNAME` is dropped, and every student is synthetic.
- **Least privilege:** the Cloud Run service account has only the Firestore user, Secret accessor and Vertex AI user roles.
