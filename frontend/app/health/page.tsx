"use client";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardHeader, ErrorBox, Input, Label, PageHeader, Spinner, Stat } from "@/components/ui";
import { num } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const tip = { contentStyle: { background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }, cursor: { fill: "var(--panel-2)" } };
const axis = { tick: { fontSize: 11, fill: "var(--muted)" }, axisLine: false, tickLine: false } as const;

export default function Health() {
  const [start, setStart] = useState("2026-11-16");
  const [end, setEnd] = useState("2026-11-27");
  const { data, error, loading } = useApi<any>("/health/timetable", { start_date: start, end_date: end });
  return (
    <div>
      <PageHeader title="Timetable Health" subtitle="How humane is the live timetable for students and staff? Computed per intake group from the real feed." right={
        <div className="flex gap-2 items-end">
          <div><Label>From</Label><Input type="date" value={start} onChange={(x) => setStart(x.target.value)} className="h-8 text-xs" /></div>
          <div><Label>To</Label><Input type="date" value={end} onChange={(x) => setEnd(x.target.value)} className="h-8 text-xs" /></div>
        </div>} />
      <ErrorBox error={error} />
      {loading && !data ? <Spinner /> : data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <Stat label="Intake groups analysed" value={num(data.summary.groups_analysed)} />
            <Stat label="Gaps > 3 h" value={num(data.summary.long_gaps)} tone="amber" sub="idle time between classes" />
            <Stat label="4+ sessions in a row" value={num(data.summary.back_to_back_4plus)} tone="red" sub="gap ≤ 30 min" />
            <Stat label="Days over 6 h" value={num(data.summary.days_over_6h)} tone="red" />
            <Stat label="Lecturers teaching" value={num(data.summary.lecturers)} />
          </div>
          <div className="grid lg:grid-cols-3 gap-4 mt-4">
            <Card>
              <CardHeader title="Days over 6 h, by weekday" />
              <div className="h-[220px] px-2 pb-3"><ResponsiveContainer>
                <BarChart data={["Mon", "Tue", "Wed", "Thu", "Fri"].map((d) => ({ day: d, n: data.long_days_by_weekday[d] || 0 }))}>
                  <CartesianGrid vertical={false} stroke="var(--grid)" /><XAxis dataKey="day" {...axis} /><YAxis {...axis} width={30} /><Tooltip {...tip} />
                  <Bar dataKey="n" name="group-days" fill="var(--red)" radius={[4, 4, 0, 0]} />
                </BarChart></ResponsiveContainer></div>
            </Card>
            <Card>
              <CardHeader title="Lecturer load" subtitle="Teaching hours per week" />
              <div className="h-[220px] px-2 pb-3"><ResponsiveContainer>
                <BarChart data={data.lecturer_load_histogram_hours_per_week}>
                  <CartesianGrid vertical={false} stroke="var(--grid)" /><XAxis dataKey="bucket" {...axis} /><YAxis {...axis} width={30} /><Tooltip {...tip} />
                  <Bar dataKey="lecturers" fill="var(--accent)" radius={[4, 4, 0, 0]} />
                </BarChart></ResponsiveContainer></div>
            </Card>
            <Card>
              <CardHeader title="Online vs physical by time of day" subtitle="Sessions starting in each hour" />
              <div className="h-[220px] px-2 pb-3"><ResponsiveContainer>
                <BarChart data={data.delivery_mix_by_hour}>
                  <CartesianGrid vertical={false} stroke="var(--grid)" /><XAxis dataKey="hour" {...axis} tickFormatter={(h: string) => h.slice(0, 2)} /><YAxis {...axis} width={34} /><Tooltip {...tip} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="physical" stackId="a" fill="var(--accent)" /><Bar dataKey="online" stackId="a" fill="var(--amber)" radius={[4, 4, 0, 0]} />
                </BarChart></ResponsiveContainer></div>
            </Card>
          </div>
          <div className="grid lg:grid-cols-3 gap-4 mt-4">
            <TableCard title="Longest days" rows={data.long_days} cols={[["intake", "Intake"], ["grouping", "Grp"], ["date", "Date"], ["hours", "Hours"]]} />
            <TableCard title="Longest gaps" rows={data.long_gaps} cols={[["intake", "Intake"], ["date", "Date"], ["between", "Between"], ["gap_hours", "Gap h"]]} />
            <TableCard title="Heaviest lecturer load" rows={data.lecturer_load} cols={[["lecturer_id", "Lecturer"], ["hours", "Hours"], ["teaching_days", "Days"]]} />
          </div>
        </>
      )}
    </div>
  );
}

function TableCard({ title, rows, cols }: { title: string; rows: any[]; cols: [string, string][] }) {
  return (
    <Card>
      <CardHeader title={title} />
      <div className="max-h-[320px] overflow-auto">
        <table className="data">
          <thead><tr>{cols.map(([, l]) => <th key={l}>{l}</th>)}</tr></thead>
          <tbody>{rows.slice(0, 40).map((r, i) => <tr key={i}>{cols.map(([k]) => <td key={k} className="tabular-nums">{r[k]}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </Card>
  );
}
