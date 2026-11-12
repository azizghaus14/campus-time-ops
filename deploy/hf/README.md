---
title: Campus Time Ops
emoji: 🗓️
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
short_description: AI operations layer for APU's live timetable
---

# Campus Time Ops — live demo

The AI operations layer for APU's timetable: plan, re-plan and run the campus, with a human approving every step.
APU Cloud Innovation Hackathon 2026 · Team Terminal.

Sign in as a demo persona (Timetabling Office, Lecturer or Student) and try:
- Lecturer MZD: **"I'm sick tomorrow, sort out my classes"**, then *Approve & apply*
- Timetabling Office: **"Monday 16 Nov is now a public holiday"**, then open **Campus** on Mon 16 / Tue 17 Nov
- Student: **"How many more classes can I miss?"**

Data: APU's public timetable feed (snapshot, staff pseudonymised), synthetic students. Emails are only ever drafts;
nothing changes without a human approval. Source code: https://github.com/azizghaus14/campus-time-ops
