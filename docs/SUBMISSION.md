# Submission form answers

**Project title:** Campus Time Ops
**Team name:** [your team name]
**Challenge:** Category 02 — Intelligent Automation & Digital Transformation
**Repository:** https://github.com/azizghaus14/campus-time-ops
**Deployed demo:** https://campus-time-ops.onrender.com (Render; kept awake by a 10-minute GitHub Actions ping)
**Pitch deck:** Campus Time Ops — Pitch Deck (PDF export)

## Project summary (paste into the form)

When a lecturer falls sick, a room floods or a public holiday is declared, APU staff re-plan classes by hand with phone calls, spreadsheets and emails. APU’s live timetable is large (about 7,656 physical sessions in a three-week window and roughly 600 on a busy day) and APSpace displays it, but nothing re-plans it.

Campus Time Ops is an AI operations layer on top of APU’s real, public timetable feed. Staff simply describe what happened, such as “I’m sick tomorrow” or “Monday 16 Nov is a public holiday”. The system works out the impact, first looks for a substitute lecturer who teaches the same module (so no student is affected), then uses Google OR-Tools to find clash-free new slots and rooms. It respects APU’s holidays, the 80% attendance rule, notice periods and the last campus shuttle, and cites the rule behind every decision. Nothing changes until a person approves; approval then creates Google Calendar events, Gmail drafts (never sent automatically) and a change-log entry, all recorded in an audit trail.

We built a FastAPI backend and an MCP server with 28 tools on Google Cloud Run, a constraint solver that re-plans a whole-campus holiday (598 sessions) in about 2.5 seconds with zero clashes, and a role-based web app for the timetabling office, lecturers and students. It has a natural-language assistant, a live 3D campus map with room heat maps, a slot finder for vivas and events, timetable health insights, and an attendance forecast that tells students how many more classes they can miss. Staff names are pseudonymised and all students are synthetic. The same tools are ready for Gemini agents.
