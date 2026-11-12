# Metrics (measured from the system)

`make bench` (`scripts/benchmark.py`) produced these figures on the committed snapshot `timetable_2026-11-12.json`, on a MacBook (Apple Silicon) with the demo clock at Thu 12 Nov 2026 09:00 MYT. The raw output is in `docs/metrics.json`. Re-run the benchmark after refreshing the snapshot.

## Solver time per disruption type
| Type | Cases | Sessions (total) | Median solve | Max solve | Clash-free |
|---|---|---|---|---|---|
| Lecturer unavailable (the 10 busiest lecturers on Fri 13 Nov) | 10 | 33 | 0.001 s | 0.018 s | ✅ all |
| Room unavailable (the 5 busiest classrooms, Mon–Fri) | 5 | 101 | 0.067 s | 0.077 s | ✅ all |
| Whole-campus holiday (Mon 16, Tue 17, Wed 18 Nov) | 3 | 1,806 | **2.57 s** | 2.63 s | ✅ all |

Every solve is followed by an independent clash checker that compares each moved session against the whole timetable. Every case reported zero group, lecturer or room clashes. A whole-campus holiday solves as **one CP-SAT model to OPTIMAL in about 2.5 s**, well under the 10-second target. Splitting by school is also implemented and tested.

## How sessions were resolved
| Type | Substitute lecturer | Rescheduled (physical) | Online fallback | Unresolved |
|---|---|---|---|---|
| Lecturer unavailable | **22 (67%)** | 11 (33%) | 0 | 0 |
| Room unavailable | – | 101 (100%; 50 of these are room-only swaps at the same time) | 0 | 0 |
| Whole-campus holiday | – | 1,696 (93.9%) | 101 (5.6%) | 9 (0.5%) |

Holiday online fallbacks are almost all evening physical classes. Under the shuttle rule (R-SHUTTLE) a physical make-up class must end by 19:00, so these classes move to daytime where possible and otherwise go online.

## Scale of each disruption
| Case | Sessions | Intake groups | Students (mock sizes) |
|---|---|---|---|
| Demo "I'm sick tomorrow" (MZD, Fri 13 Nov) | 3 | 12 | ~513 |
| Demo "Room B-04-03 flooded until Friday" (now to Fri 13 Nov) | 3 (2 handled as room-only swaps, solved in 0.009 s) | 6 | ~229 |
| Holiday Mon 16 Nov | 598 | 987 | ~37,264 |

## Actions automated per disruption (one approval click)
| Case | Calendar events | Gmail drafts | Change-log entries | Audit events |
|---|---|---|---|---|
| Sick lecturer, 4 sessions rescheduled (RVK) | 4 | 6 | 1 | 5+ |
| Demo MZD (2 substitutes + 1 reschedule) | 3 | 14 | 1 | 5+ |
| Campus holiday (597 placed) | 597 | 378 | 1 | 5+ |

## Staff time saved (estimate)
- **Baseline:** `TBD-interview`. The dashboard's placeholder assumes 20 minutes of manual effort per re-planned session: finding a slot, checking clashes, booking a room, and emailing the lecturer and groups. Replace this with figures from team interviews.
- **Interview quotes:** `TBD-interview` (1–2 APU lecturers or programme admins: how rescheduling, viva scheduling and attendance follow-up work today, and how long each takes).
- **Formula:** hours saved = sessions re-planned × baseline minutes ÷ 60. A campus holiday is 597 sessions × 20 min ≈ **199 staff-hours** (placeholder baseline).

## Attendance Risk (synthetic students)
There are 3,005 synthetic students in 150 real intakes. 462 are below the threshold now and 1,297 are at risk (score ≥ 30). These numbers reflect the generator's profile mix, not real APU data. The `max_more_absences` figure matches an independent brute-force hand calculation for 3 test students (`tests/test_attendance.py`).
