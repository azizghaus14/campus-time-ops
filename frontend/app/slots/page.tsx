"use client";
import { CalendarPlus, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { MultiPicker } from "@/components/pickers";
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, Input, Label, PageHeader, Select } from "@/components/ui";
import { post } from "@/lib/api";
import { fmtDate } from "@/lib/format";

const PRESETS = [
  { name: "FYP vivas APD3F2605CS (6 × 45 min, panel of 3)", groups: [] as string[], lecturers: ["CMM", "MSB", "RJR"], duration: 45, count: 6, room: "presentation", title: "FYP vivas - APD3F2605CS" },
  { name: "Guest talk for 3 intakes (2 h)", groups: ["AFCF2509BA", "AFCF2509ICT", "AFCF2609BA"], lecturers: [] as string[], duration: 120, count: 1, room: "auditorium", title: "Guest talk" },
];

export default function SlotFinder() {
  const router = useRouter();
  const [groups, setGroups] = useState<string[]>(PRESETS[0].groups);
  const [lects, setLects] = useState<string[]>(PRESETS[0].lecturers);
  const [duration, setDuration] = useState(45);
  const [count, setCount] = useState(6);
  const [room, setRoom] = useState("presentation");
  const [start, setStart] = useState("2026-11-16");
  const [end, setEnd] = useState("2026-11-20");
  const [title, setTitle] = useState(PRESETS[0].title);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);

  function preset(p: (typeof PRESETS)[number]) {
    setGroups(p.groups); setLects(p.lecturers); setDuration(p.duration); setCount(p.count); setRoom(p.room); setTitle(p.title); setRes(null);
  }

  async function find() {
    setBusy("find"); setErr(null);
    try {
      setRes(await post("/slots/find", { groups, lecturer_ids: lects, duration_min: duration, count, window: { start, end }, room_requirements: room ? { type: room } : null, top_n: 3 }));
    } catch (e) { setErr(e); } finally { setBusy(null); }
  }
  async function book(o: any) {
    setBusy(o.start); setErr(null);
    try {
      const p = await post("/slots/propose", { title, slot: o, groups, lecturer_ids: lects, room: o.room, description: `Booked via Slot Finder (${count > 1 ? `${count} × ${duration} min` : `${duration} min`})` });
      router.push(`/proposals/${p.id}`);
    } catch (e) { setErr(e); setBusy(null); }
  }

  const days = res ? [...new Set<string>(res.options.map((o: any) => o.date))].sort() : [];
  return (
    <div>
      <PageHeader title="Slot Finder" subtitle="Find a time when the student groups, 2–3 examiners and a suitable room are all free — vivas, presentations, make-up classes, events. Same rules as Replan (holidays, notice, shuttle)." />
      <div className="grid xl:grid-cols-[360px_1fr] gap-4">
        <Card className="p-4 space-y-3 h-fit">
          <div className="flex flex-wrap gap-1.5">{PRESETS.map((p) => <button key={p.name} onClick={() => preset(p)} className="text-[11px] rounded-md border border-[var(--border)] px-2 py-1 hover:bg-[var(--panel-2)]">{p.name}</button>)}</div>
          <div><Label>Title</Label><Input value={title} onChange={(e) => setTitle(e.target.value)} /></div>
          <div><Label hint="whole intake, all groupings">Student groups</Label><MultiPicker kind="intakes" values={groups} onChange={setGroups} placeholder="Search intake…" /></div>
          <div><Label hint="supervisor, second marker…">Examiners / lecturers</Label><MultiPicker kind="lecturers" values={lects} onChange={setLects} placeholder="Search lecturer…" /></div>
          <div className="grid grid-cols-2 gap-2">
            <div><Label>Duration (min)</Label><Input type="number" value={duration} onChange={(e) => setDuration(+e.target.value)} /></div>
            <div><Label hint="back-to-back">How many</Label><Input type="number" min={1} max={12} value={count} onChange={(e) => setCount(+e.target.value)} /></div>
          </div>
          <div><Label>Room type</Label>
            <Select value={room} onChange={(e) => setRoom(e.target.value)}>
              <option value="">Any physical room</option><option value="presentation">Presentation room</option><option value="discussion">Discussion room</option>
              <option value="classroom">Classroom</option><option value="auditorium">Auditorium</option><option value="lab">Lab</option><option value="online">Online</option>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div><Label>From</Label><Input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></div>
            <div><Label>To</Label><Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></div>
          </div>
          <ErrorBox error={err} />
          <Button className="w-full" onClick={find} loading={busy === "find"}><Search className="h-4 w-4" /> Find slots</Button>
        </Card>

        <div className="space-y-4">
          {!res ? <Card><Empty>Pick groups and examiners, then Find slots.</Empty></Card> : (
            <>
              <div className="text-sm muted">{res.feasible_slots} feasible start times in the window · headcount {res.request.headcount} · eliminated: {Object.entries(res.eliminated).map(([k, v]) => `${k} ×${v}`).join(", ") || "none"}</div>
              <div className="grid md:grid-cols-3 gap-3">
                {res.options.length === 0 && <Card className="md:col-span-3"><Empty>No common slot. Widen the window, relax the room type or drop an examiner.</Empty></Card>}
                {res.options.map((o: any) => (
                  <Card key={o.start} className="p-4">
                    <div className="flex items-center justify-between"><Badge tone="accent">#{o.rank}</Badge><span className="text-xs muted">score {o.score}</span></div>
                    <div className="text-lg font-semibold mt-2">{o.label}</div>
                    <div className="text-sm">{o.room}</div>
                    <p className="text-xs muted mt-2">{o.reason}</p>
                    {o.sub_slots && <div className="flex flex-wrap gap-1 mt-2">{o.sub_slots.map((x: any, i: number) => <span key={i} className="mono text-[10px] rounded bg-[var(--panel-2)] px-1.5 py-0.5">{x.start.slice(11, 16)}</span>)}</div>}
                    {o.rooms?.length > 1 && <div className="text-[11px] muted mt-2">Other rooms: {o.rooms.slice(1).join(", ")}</div>}
                    <Button className="w-full mt-3" size="sm" loading={busy === o.start} onClick={() => book(o)}><CalendarPlus className="h-3.5 w-3.5" /> Draft invites (needs approval)</Button>
                  </Card>
                ))}
              </div>
              {res.options.length > 0 && (
                <Card>
                  <CardHeader title="Calendar view" subtitle="Ranked options in context (08:30–21:00)" />
                  <div className="grid px-4 pb-4 gap-2" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}>
                    {days.map((d) => (
                      <div key={d}>
                        <div className="text-xs font-medium mb-1">{fmtDate(d)}</div>
                        <div className="relative h-[300px] rounded-lg bg-[var(--panel-2)]">
                          {res.options.filter((o: any) => o.date === d).map((o: any) => {
                            const s = +o.start.slice(11, 13) * 60 + +o.start.slice(14, 16), e = +o.end.slice(11, 13) * 60 + +o.end.slice(14, 16);
                            const top = ((s - 510) / 750) * 100, h = ((e - s) / 750) * 100;
                            return <div key={o.start} className="absolute left-1 right-1 rounded-md bg-[var(--accent)] text-white text-[10px] px-1.5 py-1 overflow-hidden" style={{ top: `${top}%`, height: `${Math.max(h, 7)}%` }}>#{o.rank} {o.label.split(" ").pop()}</div>;
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
