"use client";
import { ChevronLeft, ChevronRight, MapPin, Users } from "lucide-react";
import { useMemo, useState } from "react";

import { Card, PageHeader, Spinner } from "@/components/ui";
import { cn, fmtDate } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

const START = 8 * 60, END = 21 * 60, PX = 1.05; // px per minute
const mins = (iso: string) => parseInt(iso.slice(11, 13)) * 60 + parseInt(iso.slice(14, 16));
const addDays = (d: string, n: number) => { const x = new Date(d + "T12:00:00+08:00"); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };
const monday = (d: string) => { const wd = new Date(d + "T12:00:00+08:00").getUTCDay(); return addDays(d, wd === 0 ? -6 : 1 - wd); };

const PALETTE = ["#8b7cff", "#4f8dff", "#c084fc", "#38bdf8", "#f472b6", "#a3e635", "#fbbf24"];

export default function Week() {
  const session = useSession();
  const { data: health } = useApi<any>("/health");
  const [offset, setOffset] = useState(0);
  const today = health?.now?.slice(0, 10);
  const wk0 = today ? addDays(monday(today), offset * 7) : null;
  const wk4 = wk0 ? addDays(wk0, 4) : null;
  const path = !session || !wk0 ? null : session.role === "lecturer" ? `/lecturers/${session.user}/schedule` : session.role === "student" ? "/me" : null;
  const { data: lec } = useApi<any>(session?.role === "lecturer" ? path : null, { start_date: wk0, end_date: wk4 });
  const { data: me } = useApi<any>(session?.role === "student" ? "/me" : null);
  const { data: grp } = useApi<any>(me && wk0 ? `/groups/${me.intake}/schedule` : null, { start_date: wk0, end_date: wk4, grouping: me?.grouping });

  const sessions: any[] = (session?.role === "lecturer" ? lec?.sessions : grp?.sessions) || [];
  const colors = useMemo(() => {
    const m: Record<string, string> = {};
    [...new Set(sessions.map((s) => s.module_name))].sort().forEach((n, i) => (m[n] = PALETTE[i % PALETTE.length]));
    return m;
  }, [sessions]);
  if (!session || !wk0) return <Spinner />;
  const days = [0, 1, 2, 3, 4].map((i) => addDays(wk0, i));
  const nowMin = health ? mins(health.now) : 0;
  const moved = sessions.filter((s) => s.moved_by);
  const hours = sessions.reduce((a, s) => a + s.duration_min, 0) / 60;

  return (
    <div>
      <PageHeader title={session.role === "lecturer" ? "My week" : "My timetable"}
        subtitle={session.role === "lecturer" ? `${session.name} · straight from APU's live timetable` : `${me?.intake ?? ""} / ${me?.grouping ?? ""} · straight from APU's live timetable`}
        right={
          <div className="flex items-center gap-2">
            <button onClick={() => setOffset((o) => o - 1)} className="h-9 w-9 grid place-items-center rounded-full bg-white/[0.05] hover:bg-white/[0.1]"><ChevronLeft className="h-4 w-4" /></button>
            <div className="text-[13px] tabular-nums min-w-[150px] text-center">{fmtDate(days[0], { day: "numeric", month: "short" })} – {fmtDate(days[4], { day: "numeric", month: "short" })}</div>
            <button onClick={() => setOffset((o) => o + 1)} className="h-9 w-9 grid place-items-center rounded-full bg-white/[0.05] hover:bg-white/[0.1]"><ChevronRight className="h-4 w-4" /></button>
          </div>} />
      <div className="grid grid-cols-3 gap-3 mb-4 max-w-[640px]">
        <Card className="px-4 py-3"><div className="text-[24px] font-semibold tabular-nums">{sessions.length}</div><div className="faint text-[12px]">sessions this week</div></Card>
        <Card className="px-4 py-3"><div className="text-[24px] font-semibold tabular-nums">{hours.toFixed(1)}h</div><div className="faint text-[12px]">in class</div></Card>
        <Card className="px-4 py-3"><div className={cn("text-[24px] font-semibold tabular-nums", moved.length > 0 && "text-[var(--green)]")}>{moved.length}</div><div className="faint text-[12px]">changed by a re-plan</div></Card>
      </div>
      <Card className="p-4 overflow-x-auto">
        <div className="grid min-w-[760px]" style={{ gridTemplateColumns: "52px repeat(5, 1fr)" }}>
          <div />
          {days.map((d) => (
            <div key={d} className={cn("pb-3 text-center", d === today && "text-[var(--accent)]")}>
              <div className="text-[11px] faint uppercase tracking-wider">{fmtDate(d, { weekday: "short" })}</div>
              <div className={cn("text-[20px] font-semibold tabular-nums mx-auto mt-0.5 h-9 w-9 grid place-items-center rounded-full", d === today && "bg-[var(--accent)] text-white")}>{fmtDate(d, { day: "numeric" })}</div>
            </div>
          ))}
          <div className="relative" style={{ height: (END - START) * PX }}>
            {Array.from({ length: 14 }, (_, i) => <div key={i} className="absolute right-2 text-[10.5px] faint tabular-nums -translate-y-1/2" style={{ top: i * 60 * PX }}>{String(8 + i).padStart(2, "0")}:00</div>)}
          </div>
          {days.map((d) => (
            <div key={d} className="relative border-l border-white/[0.05]" style={{ height: (END - START) * PX }}>
              {Array.from({ length: 14 }, (_, i) => <div key={i} className="absolute inset-x-0 border-t border-white/[0.04]" style={{ top: i * 60 * PX }} />)}
              {d === today && nowMin > START && nowMin < END && (
                <div className="absolute inset-x-0 z-10 flex items-center" style={{ top: (nowMin - START) * PX }}><span className="h-2 w-2 rounded-full bg-[var(--red)] -ml-1" /><span className="flex-1 h-px bg-[var(--red)]" /></div>
              )}
              {sessions.filter((s) => s.date === d).map((s) => {
                const top = (mins(s.start) - START) * PX, h = Math.max(26, s.duration_min * PX - 3);
                const c = colors[s.module_name];
                return (
                  <div key={s.id} className={cn("absolute left-1 right-1 rounded-xl px-2.5 py-1.5 overflow-hidden border", s.moved_by ? "border-[var(--green)]/70" : "border-white/[0.08]")}
                    style={{ top, height: h, background: `linear-gradient(180deg, ${c}38, ${c}18)`, boxShadow: `inset 3px 0 0 ${c}` }}
                    title={`${s.module_name} ${s.time} ${s.room}`}>
                    <div className="text-[12px] font-semibold leading-tight truncate">{s.module_name}</div>
                    {h > 40 && <div className="text-[10.5px] text-white/60 mt-0.5 flex items-center gap-1 truncate"><MapPin className="h-2.5 w-2.5 shrink-0" />{s.room === "ONLINE" ? "Online" : s.room}</div>}
                    {h > 56 && <div className="text-[10.5px] text-white/50 flex items-center gap-1"><Users className="h-2.5 w-2.5" />{session.role === "lecturer" ? `${s.n_groups} group(s)` : s.lecturer_name}</div>}
                    {s.moved_by && <div className="absolute right-1.5 top-1.5 text-[9px] font-bold text-[var(--green)]">MOVED</div>}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </Card>
      {moved.length > 0 && (
        <Card className="mt-4 p-4">
          <div className="text-[13px] font-semibold mb-2">What changed</div>
          {moved.map((s) => <div key={s.id} className="text-[12.5px] muted">{s.module_name}: now {fmtDate(s.date)} {s.time} in {s.room} (plan {s.moved_by})</div>)}
        </Card>
      )}
    </div>
  );
}
