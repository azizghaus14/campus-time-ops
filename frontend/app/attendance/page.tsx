"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Badge, Card, CardHeader, Empty, ErrorBox, PageHeader, Spinner, Stat } from "@/components/ui";
import { fmtDate, num } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

export default function Page() {
  return <Suspense fallback={<Spinner />}><Attendance /></Suspense>;
}

function Spark({ data }: { data: number[] }) {
  if (!data?.length) return null;
  const w = 70, h = 20, lo = Math.min(70, ...data), hi = 100;
  const pts = data.map((v, i) => `${(i / Math.max(1, data.length - 1)) * w},${h - ((v - lo) / (hi - lo)) * h}`).join(" ");
  const y80 = h - ((80 - lo) / (hi - lo)) * h;
  return (
    <svg width={w} height={h} className="overflow-visible">
      <line x1={0} x2={w} y1={y80} y2={y80} stroke="var(--red)" strokeDasharray="2 2" strokeWidth={1} />
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
    </svg>
  );
}

function Attendance() {
  const sp = useSearchParams();
  const router = useRouter();
  const session = useSession();
  const isStudent = session?.role === "student";
  const sel = isStudent ? session!.user : sp.get("student") || "STU-DEMO-01";
  const list = useApi<any>(session && !isStudent ? "/attendance/risk" : null, { limit: 150 });
  const one = useApi<any>(session ? `/attendance/students/${sel}` : null);
  const f = one.data?.forecast;
  return (
    <div>
      <PageHeader title={isStudent ? "My attendance" : "Attendance Risk"} subtitle={isStudent ? "Forecast from your intake group's real remaining sessions. 80% applies to each module." : "Read-only. Students below or heading towards the attendance threshold, forecast from each intake group's real remaining sessions. All students are synthetic."} />
      {!isStudent && <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Stat label="Students (synthetic)" value={num(list.data?.students_total)} />
        <Stat label="Below threshold now" value={num(list.data?.below_threshold)} tone="red" />
        <Stat label="At risk" value={num(list.data?.at_risk)} tone="amber" sub="score ≥ 30: slipping with ≤ 2 absences left, below or projected below, 3+ in a row" />
        <Stat label="Threshold" value={list.data ? `${Math.round(list.data.threshold * 100)}%` : "–"} sub="ATTENDANCE_THRESHOLD · APU rule to VERIFY" />
      </div>}
      <div className={isStudent ? "grid gap-4 max-w-[560px]" : "grid xl:grid-cols-[1fr_440px] gap-4"}>
        {!isStudent && <Card>
          <CardHeader title="Risk table" subtitle="Ranked by risk score" />
          <ErrorBox error={list.error} />
          {list.loading && !list.data ? <Spinner label="Forecasting ~3,000 students…" /> : (
            <div className="max-h-[680px] overflow-auto">
              <table className="data">
                <thead><tr><th>Student</th><th>Intake</th><th>Now</th><th>Trend</th><th>Can miss</th><th>Projected</th><th>Why</th></tr></thead>
                <tbody>
                  {list.data?.students.map((s: any) => (
                    <tr key={s.student_id} onClick={() => router.push(`/attendance?student=${s.student_id}`)} className={`cursor-pointer ${s.student_id === sel ? "[&>td]:bg-[var(--accent-soft)]" : ""}`}>
                      <td><div className="font-medium">{s.name}</div><div className="muted text-[11px]">{s.student_id}</div></td>
                      <td className="text-xs">{s.intake}/{s.grouping}</td>
                      <td className="tabular-nums">{s.current_percent}%</td>
                      <td><Spark data={s.weekly} /></td>
                      <td>{s.max_more_absences < 0 ? <Badge tone="red">cannot reach</Badge> : <Badge tone={s.max_more_absences <= 1 ? "red" : "amber"}>{s.max_more_absences} more</Badge>}</td>
                      <td className="tabular-nums">{s.projected_percent_end}%</td>
                      <td className="text-[11px] muted max-w-[260px]">{s.reasons.join("; ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>}
        <div className="space-y-4">
          {one.loading && !one.data ? <Card><Spinner /></Card> : one.error ? <ErrorBox error={one.error} /> : f && (
            <>
              <Card className="p-4">
                <div className="muted text-xs">{one.data.student.id} · {f.intake}/{f.grouping}</div>
                <div className="text-lg font-semibold">{f.name}</div>
                <div className="grid grid-cols-3 gap-2 mt-3 text-center">
                  <div className="rounded-lg bg-[var(--panel-2)] py-2"><div className="text-xl font-semibold">{f.current_percent}%</div><div className="muted text-[11px]">attendance now</div></div>
                  <div className="rounded-lg bg-[var(--panel-2)] py-2"><div className="text-xl font-semibold">{f.remaining_sessions}</div><div className="muted text-[11px]">sessions left</div></div>
                  <div className="rounded-lg bg-[var(--panel-2)] py-2"><div className="text-xl font-semibold">{f.projected_percent_end}%</div><div className="muted text-[11px]">projected end</div></div>
                </div>
                <div className={`mt-3 rounded-xl p-3 ${f.max_more_absences < 0 ? "bg-[var(--red-soft)]" : f.max_more_absences <= 2 ? "bg-[var(--amber-soft)]" : "bg-[var(--green-soft)]"}`}>
                  <div className="text-[13px]">{f.max_more_absences < 0 ? "Cannot reach the threshold in" : "You can miss at most"}</div>
                  <div className="text-3xl font-semibold tabular-nums">{f.max_more_absences < 0 ? f.binding_module : <>{f.max_more_absences} more class{f.max_more_absences === 1 ? "" : "es"}</>}</div>
                  {f.max_more_absences >= 0 && f.binding_module && <div className="text-xs muted">binding module: {f.binding_module}</div>}
                </div>
                <p className="text-sm mt-3">“{f.message}”</p>
                <p className="muted text-[11px] mt-2">{f.method}. {f.remaining_in_published_timetable} of the remaining sessions are in the published feed window.</p>
              </Card>
              <Card>
                <CardHeader title="Forecast" subtitle="Cumulative attendance by week vs threshold" />
                <div className="h-[200px] px-2 pb-3"><ResponsiveContainer>
                  <LineChart data={f.weekly}>
                    <CartesianGrid vertical={false} stroke="var(--grid)" />
                    <XAxis dataKey="week_start" tickFormatter={(d: string) => fmtDate(d, { day: "2-digit", month: "short" })} tick={{ fontSize: 10, fill: "var(--muted)" }} axisLine={false} tickLine={false} />
                    <YAxis domain={[50, 100]} tick={{ fontSize: 10, fill: "var(--muted)" }} axisLine={false} tickLine={false} width={30} unit="%" />
                    <Tooltip contentStyle={{ background: "var(--panel-solid)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} />
                    <ReferenceLine y={f.threshold * 100} stroke="var(--red)" strokeDasharray="4 3" label={{ value: `${Math.round(f.threshold * 100)}%`, fill: "var(--red)", fontSize: 10, position: "insideTopRight" }} />
                    {f.projected_percent_end != null && <ReferenceLine y={f.projected_percent_end} stroke="var(--amber)" strokeDasharray="2 3" label={{ value: "projected", fill: "var(--amber)", fontSize: 10, position: "insideBottomRight" }} />}
                    <Line dataKey="cumulative_percent" name="cumulative" stroke="var(--accent)" strokeWidth={2} dot={false} />
                    <Line dataKey="week_percent" name="that week" stroke="var(--muted)" strokeWidth={1} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer></div>
              </Card>
              <Card>
                <CardHeader title="Per module" subtitle="80% applies to each module (HB §2.2)" />
                <table className="data">
                  <thead><tr><th>Module</th><th>Held</th><th>%</th><th>Left</th><th>Can miss</th></tr></thead>
                  <tbody>{f.per_module.map((m: any) => (
                    <tr key={m.module} className={m.module === f.binding_module ? "[&>td]:font-semibold" : ""}>
                      <td className="max-w-[170px]">{m.module}</td><td className="tabular-nums">{m.attended}/{m.held}</td><td className="tabular-nums">{m.percent ?? "–"}</td><td className="tabular-nums">{m.remaining}</td>
                      <td>{m.max_more_absences < 0 ? <Badge tone="red">–</Badge> : m.max_more_absences}</td>
                    </tr>))}</tbody>
                </table>
              </Card>
              {f.next_class && <Card className="p-3 text-xs">Next class: <b>{f.next_class.module}</b> · {fmtDate(f.next_class.date)} {f.next_class.time} · {f.next_class.room}</Card>}
            </>
          )}
          {!f && !one.loading && <Card><Empty>Select a student.</Empty></Card>}
        </div>
      </div>
    </div>
  );
}
