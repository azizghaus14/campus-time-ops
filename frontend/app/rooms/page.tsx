"use client";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardHeader, ErrorBox, Input, Label, PageHeader, Select, Spinner, Stat } from "@/components/ui";
import { useApi } from "@/lib/use-api";

function heat(v: number) {
  // 0 -> panel, 1 -> accent
  const a = Math.round(Math.min(1, v) * 100);
  return `color-mix(in srgb, var(--accent) ${a}%, var(--panel-2))`;
}

export default function Rooms() {
  const [start, setStart] = useState("2026-11-16");
  const [end, setEnd] = useState("2026-11-20");
  const [type, setType] = useState("");
  const [at, setAt] = useState("2026-11-12T15:00");
  const [sort, setSort] = useState("avg");
  const u = useApi<any>("/rooms/utilisation", { start_date: start, end_date: end, room_type: type || undefined });
  const e = useApi<any>("/rooms/empty-now", { at: at ? `${at}:00+08:00` : undefined });
  const rows = useMemo(() => {
    const r = [...(u.data?.rooms || [])];
    if (sort === "avg") r.sort((a, b) => b.avg - a.avg);
    else r.sort((a, b) => a.room.localeCompare(b.room));
    return r;
  }, [u.data, sort]);

  return (
    <div>
      <PageHeader title="Rooms" subtitle="Room × hour utilisation from the live timetable, per block, and which rooms are empty right now. Replan and Slot Finder use the same free-room index." />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Stat label="Campus utilisation (avg, 08–21h)" value={u.data ? `${Math.round(u.data.campus_avg * 100)}%` : "–"} sub={`${u.data?.range.working_days ?? "–"} working days`} tone="accent" />
        <Stat label="Rooms analysed" value={u.data?.rooms.length ?? "–"} sub={type || "all physical rooms"} />
        <Stat label="Empty right now" value={e.data?.empty_count ?? "–"} sub={e.data ? `${Math.round(e.data.share_empty * 100)}% of physical rooms` : ""} tone="green" />
        <Stat label="In use right now" value={e.data?.in_use_count ?? "–"} tone="amber" />
      </div>
      <div className="grid xl:grid-cols-[1fr_340px] gap-4">
        <Card>
          <CardHeader title="Utilisation heatmap" subtitle="Share of each hour the room is booked, averaged over working days" right={
            <div className="flex gap-2 items-end">
              <div><Label>From</Label><Input type="date" value={start} onChange={(x) => setStart(x.target.value)} className="h-8 text-xs" /></div>
              <div><Label>To</Label><Input type="date" value={end} onChange={(x) => setEnd(x.target.value)} className="h-8 text-xs" /></div>
              <div><Label>Type</Label><Select value={type} onChange={(x) => setType(x.target.value)} className="h-8 text-xs w-32"><option value="">All</option><option value="classroom">Classroom</option><option value="lab">Lab</option><option value="specialist_lab">Specialist</option><option value="auditorium">Auditorium</option><option value="discussion">Discussion</option><option value="presentation">Presentation</option></Select></div>
              <div><Label>Sort</Label><Select value={sort} onChange={(x) => setSort(x.target.value)} className="h-8 text-xs w-24"><option value="avg">Busiest</option><option value="name">Name</option></Select></div>
            </div>} />
          <ErrorBox error={u.error} />
          {u.loading && !u.data ? <Spinner /> : u.data && (
            <div className="max-h-[640px] overflow-auto px-4 pb-4">
              <table className="text-[11px] border-separate border-spacing-[2px]">
                <thead><tr><th className="sticky top-0 bg-[var(--panel)] text-left muted font-medium pr-2">Room</th>{u.data.hours.map((h: string) => <th key={h} className="sticky top-0 bg-[var(--panel)] muted font-normal w-9">{h.slice(0, 2)}</th>)}<th className="sticky top-0 bg-[var(--panel)] muted font-medium pl-2">avg</th></tr></thead>
                <tbody>
                  {rows.map((r: any) => (
                    <tr key={r.room}>
                      <td className="pr-2 whitespace-nowrap max-w-[220px] truncate" title={`${r.room} · ${r.type} · cap ${r.capacity}`}>{r.room}</td>
                      {r.hours.map((v: number, i: number) => <td key={i} title={`${r.room} ${u.data.hours[i]}: ${Math.round(v * 100)}%`} className="h-5 w-9 rounded-[3px]" style={{ background: heat(v) }} />)}
                      <td className="pl-2 tabular-nums">{Math.round(r.avg * 100)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader title="Utilisation per block" />
            <div className="h-[220px] px-2 pb-3">
              <ResponsiveContainer>
                <BarChart data={(u.data?.by_block || []).map((b: any) => ({ ...b, pct: Math.round(b.utilisation * 100) }))} layout="vertical" margin={{ left: 8 }}>
                  <CartesianGrid horizontal={false} stroke="var(--grid)" />
                  <XAxis type="number" unit="%" tick={{ fontSize: 11, fill: "var(--muted)" }} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="block" width={42} tick={{ fontSize: 11, fill: "var(--muted)" }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} cursor={{ fill: "var(--panel-2)" }} formatter={(v: any, _n: any, p: any) => [`${v}% (${p.payload.rooms} rooms)`, "utilisation"]} />
                  <Bar dataKey="pct" fill="var(--accent)" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card>
            <CardHeader title="Empty rooms right now" subtitle="Free until their next class" right={<Input type="datetime-local" value={at} onChange={(x) => setAt(x.target.value)} className="h-8 text-xs w-44" />} />
            <div className="max-h-[360px] overflow-auto">
              <table className="data">
                <thead><tr><th>Room</th><th>Type</th><th>Cap</th><th>Free until</th></tr></thead>
                <tbody>{(e.data?.rooms || []).slice(0, 80).map((r: any) => <tr key={r.room}><td>{r.room}</td><td className="muted">{r.type}</td><td>{r.capacity}</td><td className="tabular-nums">{r.free_until}</td></tr>)}</tbody>
              </table>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
