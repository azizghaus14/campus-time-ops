"use client";
import { ArrowRight, CloudRain, HeartPulse, PartyPopper } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Badge, Button, Card, CardHeader, Empty, ErrorBox, PageHeader, Spinner, Stat } from "@/components/ui";
import { post } from "@/lib/api";
import { fmtDate, num } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const DEMO_LECTURER = "MZD";

const SCENARIOS = [
  { key: "sick", icon: HeartPulse, title: `"I'm sick tomorrow" (lecturer ${DEMO_LECTURER})`, sub: "Fri 13 Nov · substitutes first, then reschedule",
    body: { type: "LECTURER_UNAVAILABLE", scope: { lecturer_id: DEMO_LECTURER }, window: { start: "2026-11-13", end: "2026-11-13" }, reason: "Lecturer on medical leave", created_by: "dashboard-demo" } },
  { key: "flood", icon: CloudRain, title: `"Room B-04-03 is flooded until Friday"`, sub: "Room swaps at the same time where possible",
    body: { type: "ROOM_UNAVAILABLE", scope: { rooms: ["B-04-03"] }, window: { start: "2026-11-12T09:00:00+08:00", end: "2026-11-13" }, reason: "Flooded", created_by: "dashboard-demo" } },
  { key: "holiday", icon: PartyPopper, title: `"Monday 16 Nov is now a public holiday"`, sub: "Whole campus · ~600 physical sessions",
    body: { type: "HOLIDAY", scope: { date: "2026-11-16", name: "Public holiday (declared)" }, reason: "Government declared public holiday", created_by: "dashboard-demo" } },
];

export default function Overview() {
  const { data, error, loading } = useApi<any>("/overview", undefined, 15000);
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);

  async function launch(s: (typeof SCENARIOS)[number]) {
    setBusy(s.key);
    setErr(null);
    try {
      const d = await post<any>("/disruptions", s.body);
      router.push(`/disruptions?id=${d.id}&autoplan=1`);
    } catch (e) {
      setErr(e);
      setBusy(null);
    }
  }

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  const k = data.kpis;
  return (
    <div>
      <PageHeader title="Overview" subtitle={<>APU&apos;s live timetable ({num(data.rows)} intake-session rows → {num(data.physical_sessions)} physical sessions, {num(data.intakes)} intakes, {num(data.lecturers)} lecturers, {num(data.rooms)} rooms) re-planned by agents — a human approves every step.</>} />

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Stat label="Sessions re-planned" value={num(k.sessions_replanned)} sub={`${k.proposals_executed} executed proposals`} tone="green" />
        <Stat label="Substitutes found" value={num(k.substitutes_found)} sub="same time & room, no student affected" tone="violet" />
        <Stat label="Median time to re-plan" value={k.median_time_to_replan_s == null ? "–" : `${k.median_time_to_replan_s}s`} sub="solver wall-clock, measured" tone="accent" />
        <Stat label="Pending approvals" value={num(k.pending_approvals)} sub="waiting for a human" tone="amber" />
        <Stat label="Students below threshold" value={num(k.students_below_threshold)} sub={`${num(k.students_at_risk)} at risk (synthetic)`} tone="red" />
      </div>

      <div className="grid lg:grid-cols-3 gap-4 mt-4">
        <Card className="lg:col-span-2">
          <CardHeader title="Try a disruption" subtitle="The three demo prompts. Each creates a disruption, shows its impact and runs the solver — nothing changes until you approve." />
          <div className="grid md:grid-cols-3 gap-3 p-4 pt-2">
            {SCENARIOS.map((s) => (
              <button key={s.key} onClick={() => launch(s)} disabled={!!busy}
                className="text-left rounded-xl border border-[var(--border)] p-3.5 hover:border-[var(--accent)] hover:bg-[var(--accent-soft)] transition disabled:opacity-60">
                <s.icon className="h-5 w-5 text-[var(--accent)]" />
                <div className="font-medium text-sm mt-2 leading-snug">{s.title}</div>
                <div className="muted text-xs mt-1">{s.sub}</div>
                <div className="text-xs text-[var(--accent)] mt-2 flex items-center gap-1">{busy === s.key ? "Creating…" : <>Run <ArrowRight className="h-3 w-3" /></>}</div>
              </button>
            ))}
          </div>
          {!!err && <div className="px-4 pb-4"><ErrorBox error={err} /></div>}
        </Card>
        <Card>
          <CardHeader title="Sessions per day" subtitle="Physical sessions this week (from the snapshot)" />
          <div className="h-[170px] px-2 pb-2">
            <ResponsiveContainer>
              <BarChart data={data.week_sessions_per_day}>
                <CartesianGrid vertical={false} stroke="var(--grid)" />
                <XAxis dataKey="day" tick={{ fontSize: 11, fill: "var(--muted)" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "var(--muted)" }} axisLine={false} tickLine={false} width={32} />
                <Tooltip contentStyle={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} cursor={{ fill: "var(--panel-2)" }} />
                <Bar dataKey="sessions" fill="var(--accent)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="grid lg:grid-cols-3 gap-4 mt-4">
        <Card>
          <CardHeader title="Active disruptions" right={<Link className="text-xs text-[var(--accent)]" href="/disruptions">All →</Link>} />
          {data.disruptions_active.length === 0 ? <Empty>No open disruptions.</Empty> : (
            <ul className="px-4 pb-4 space-y-2">
              {data.disruptions_active.map((d: any) => (
                <li key={d.id}>
                  <Link href={`/disruptions?id=${d.id}`} className="block rounded-lg border border-[var(--border)] p-2.5 hover:bg-[var(--panel-2)]">
                    <div className="flex items-center gap-2"><Badge tone="red">{d.type.replace("_", " ")}</Badge><span className="text-xs muted">{d.id}</span><Badge>{d.status}</Badge></div>
                    <div className="text-xs mt-1">{d.headline}</div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card>
          <CardHeader title="Pending approvals" right={<Link className="text-xs text-[var(--accent)]" href="/proposals">All →</Link>} />
          {data.pending_approvals.length === 0 ? <Empty>Nothing waiting for approval.</Empty> : (
            <ul className="px-4 pb-4 space-y-2">
              {data.pending_approvals.map((p: any) => (
                <li key={p.id}>
                  <Link href={`/proposals/${p.id}`} className="block rounded-lg border border-[var(--border)] p-2.5 hover:bg-[var(--panel-2)]">
                    <div className="flex items-center gap-2"><Badge tone="amber">DRAFT</Badge><span className="text-xs muted">{p.id} v{p.version}</span></div>
                    <div className="text-sm mt-1 font-medium">{p.title}</div>
                    {p.summary && p.kind === "REPLAN" && <div className="text-xs muted mt-0.5">{p.summary.substituted} substitute · {p.summary.rescheduled} rescheduled · {p.summary.placed_online} online · {p.summary.unresolved} unresolved</div>}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card>
          <CardHeader title="Attendance risk" subtitle="Synthetic students, real remaining sessions" right={<Link className="text-xs text-[var(--accent)]" href="/attendance">All →</Link>} />
          <ul className="px-4 pb-4 space-y-1.5">
            {data.attendance_top.map((s: any) => (
              <li key={s.student_id} className="flex items-center justify-between text-sm">
                <Link href={`/attendance?student=${s.student_id}`} className="hover:underline truncate">{s.name} <span className="muted text-xs">{s.intake}</span></Link>
                <span className="flex items-center gap-2 shrink-0">
                  <span className="tabular-nums text-xs">{s.current_percent}%</span>
                  <Badge tone={s.max_more_absences < 0 ? "red" : "amber"}>{s.max_more_absences < 0 ? "can't reach 80%" : `${s.max_more_absences} more`}</Badge>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <p className="muted text-[11px] mt-4">Snapshot {data.snapshot?.snapshot_file} · fetched {data.snapshot?.fetched_at ? fmtDate(data.snapshot.fetched_at) : "–"} · window {data.date_coverage.from} → {data.date_coverage.to} · “hours saved” basis: {k.hours_saved_basis}</p>
    </div>
  );
}
