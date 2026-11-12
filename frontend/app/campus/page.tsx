"use client";
import { Pause, Play, X } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

import type { Mode, RoomState } from "@/components/campus/scene";
import { Orb } from "@/components/orb";
import { cn, fmtDate } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

const CampusCanvas = dynamic(() => import("@/components/campus/scene"), { ssr: false, loading: () => <div className="h-screen grid place-items-center"><Orb state="shaping" size={72} halo /></div> });

const hm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

export default function Campus() {
  const session = useSession();
  const { data: layout } = useApi<any>("/campus/layout");
  const { data: health } = useApi<any>("/health");
  const [date, setDate] = useState<string | null>(null);
  const [t, setT] = useState(10 * 60 + 45);
  const [mode, setMode] = useState<Mode>("live");
  const [playing, setPlaying] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [floor, setFloor] = useState<number | null>(null);
  const [room, setRoom] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [insightsOpen, setInsightsOpen] = useState(true);

  useEffect(() => {
    if (health && !date) {
      setDate(health.now.slice(0, 10));
      const m = parseInt(health.now.slice(11, 13)) * 60 + parseInt(health.now.slice(14, 16));
      setT(Math.max(8 * 60 + 30, Math.min(20 * 60, m < 8 * 60 + 30 ? 10 * 60 + 45 : m + 60)));
    }
  }, [health, date]);
  const { data: day } = useApi<any>(date ? "/campus/day" : null, { date: date || undefined }, 20000);

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setT((x) => (x >= 20 * 60 + 45 ? 8 * 60 : x + 5)), 60);
    return () => clearInterval(id);
  }, [playing]);

  const { states, util, pins, stats } = useMemo(() => {
    const states: Record<string, RoomState> = {}, util: Record<string, number> = {};
    const pins: Record<string, { used: number; total: number; affected: number }> = {};
    let used = 0, free = 0, affected = 0;
    if (!layout || !day) return { states, util, pins, stats: null };
    const perBuilding: { id: string; name: string; used: number; total: number }[] = [];
    for (const b of layout.buildings) {
      const p = { used: 0, total: 0, affected: 0 };
      for (const f of b.floors) for (const r of f.rooms) {
        const rd = day.rooms[r.name];
        util[r.name] = mode === "week" ? rd?.week_util || 0 : rd?.util || 0;
        const cur = rd?.sessions.find((s: any) => s.s <= t && t < s.e);
        let st: RoomState = "free";
        if (cur) st = cur.affected ? "affected" : cur.pending ? "pending" : cur.moved ? "moved" : "used";
        states[r.name] = st;
        p.total += 1;
        if (st !== "free") p.used += 1;
        if (st === "affected") { p.affected += 1; affected += 1; }
        if (st === "free") free += 1; else used += 1;
      }
      pins[b.id] = p;
      perBuilding.push({ id: b.id, name: b.name, used: p.used, total: p.total });
    }
    // peak time of the day
    let peak = { t: 0, n: 0 };
    for (let m = 8 * 60 + 30; m < 21 * 60; m += 15) {
      let n = 0;
      for (const k in day.rooms) if (day.rooms[k].sessions.some((s: any) => s.s <= m && m < s.e && !s.pending)) n++;
      if (n > peak.n) peak = { t: m, n };
    }
    const busiest = [...perBuilding].sort((a, b) => b.used / b.total - a.used / a.total)[0];
    const under = Object.values(day.rooms).filter((r: any) => r.week_util < 0.15).length;
    return { states, util, pins, stats: { used, free, affected, peak, busiest, under } };
  }, [layout, day, t, mode]);

  const selB = layout?.buildings.find((b: any) => b.id === selected);
  const roomInfo = room && day ? day.rooms[room] : null;
  const roomMeta = room && layout ? layout.buildings.flatMap((b: any) => b.floors.flatMap((f: any) => f.rooms.map((r: any) => ({ ...r, building: b.name, level: f.level })))).find((r: any) => r.name === room) : null;

  if (!layout || !session) return <div className="h-[70vh] grid place-items-center"><div className="text-center"><Orb state="searching" size={72} halo /><div className="muted text-sm mt-4">Building the campus…</div></div></div>;
  return (
    <div className="relative -mx-4 md:-ml-[260px] md:-mr-8 -mt-[84px] -mb-7 h-screen overflow-hidden">
      <CampusCanvas layout={layout} states={states} util={util} mode={mode} selected={selected} floor={floor} hoverRoom={hover}
        onSelect={(id) => { setSelected(id); setFloor(null); if (!id) setRoom(null); }} onRoom={setRoom} onHover={setHover} pins={pins} />

      {/* top-left: mode */}
      <div className="absolute left-5 md:left-[284px] top-[76px] flex flex-col gap-3">
        <div className="glass-strong rounded-full p-1 flex">
          {([["live", "Live"], ["heat", "Heat · day"], ["week", "Heat · week"]] as [Mode, string][]).map(([m, l]) => (
            <button key={m} onClick={() => setMode(m)} className={cn("rounded-full px-4 py-1.5 text-[13px] transition", mode === m ? "bg-white text-black font-medium" : "text-white/70 hover:text-white")}>{l}</button>
          ))}
        </div>
        {stats && (
          <div className="glass-strong rounded-2xl px-4 py-3 w-[230px]">
            <div className="text-[11px] faint uppercase tracking-wider">{session.role === "student" ? "Study spaces" : "Right now"} · {hm(t)}</div>
            <div className="flex items-end gap-4 mt-1.5">
              <div><div className="text-[26px] font-semibold tabular-nums leading-none text-[var(--green)]">{stats.free}</div><div className="faint text-[11px] mt-1">rooms free</div></div>
              <div><div className="text-[26px] font-semibold tabular-nums leading-none text-[var(--accent)]">{stats.used}</div><div className="faint text-[11px] mt-1">in use</div></div>
              {stats.affected > 0 && <div><div className="text-[26px] font-semibold tabular-nums leading-none text-[var(--red)]">{stats.affected}</div><div className="faint text-[11px] mt-1">affected</div></div>}
            </div>
          </div>
        )}
      </div>

      {/* top-right: insights */}
      {insightsOpen && stats && (
        <div className="absolute right-5 top-[76px] glass-strong rounded-[22px] w-[300px] p-5 rise">
          <button onClick={() => setInsightsOpen(false)} className="absolute right-3 top-3 h-7 w-7 grid place-items-center rounded-full hover:bg-white/10"><X className="h-4 w-4 text-white/60" /></button>
          <Orb state="connecting" size={44} tint="violet" halo />
          <div className="font-semibold text-[16px] mt-3 tracking-tight">{3 + (day?.disruptions.filter((d: any) => d.sessions_today > 0).length || 0)} insights for {date && fmtDate(date, { weekday: "long", day: "numeric", month: "short" })}</div>
          <ul className="mt-3 space-y-2.5 text-[13px] text-white/80">
            <li className="flex gap-2"><span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-[var(--accent)] shrink-0" />Peak at <b className="text-white">{hm(stats.peak.t)}</b>: {stats.peak.n} rooms in use at once.</li>
            <li className="flex gap-2"><span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-[var(--accent)] shrink-0" /><b className="text-white">{stats.busiest?.name}</b> is the busiest building now ({stats.busiest?.used}/{stats.busiest?.total} rooms).</li>
            <li className="flex gap-2"><span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-[var(--green)] shrink-0" /><b className="text-white">{stats.under}</b> rooms are used under 15% of the week — candidates for make-up classes.</li>
            {day?.disruptions.filter((d: any) => d.sessions_today > 0).map((d: any) => (
              <li key={d.id} className="flex gap-2"><span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-[var(--red)] shrink-0" />{d.type.replace("_", " ").toLowerCase()} · <b className="text-white">{d.sessions_today}</b> sessions affected today ({d.id}).</li>
            ))}
          </ul>
          <button onClick={() => { setMode("heat"); setInsightsOpen(false); }} className="mt-4 w-full rounded-full h-9 bg-white text-black text-[13px] font-medium">Show heat map</button>
        </div>
      )}

      {/* right drawer: building / room */}
      {selB && (
        <div className="absolute right-5 bottom-28 glass-strong rounded-[22px] w-[320px] max-h-[56vh] overflow-auto p-4 rise" style={{ top: insightsOpen ? 440 : 76 }}>
          <div className="flex items-center justify-between">
            <div><div className="font-semibold tracking-tight">{selB.name}</div><div className="faint text-[11.5px]">{selB.rooms} rooms · {selB.floors.length} floors · click a room</div></div>
            <button onClick={() => { setSelected(null); setRoom(null); }} className="h-7 w-7 grid place-items-center rounded-full hover:bg-white/10"><X className="h-4 w-4 text-white/60" /></button>
          </div>
          <div className="flex flex-wrap gap-1 mt-3">
            <button onClick={() => setFloor(null)} className={cn("rounded-full px-2.5 py-1 text-[11.5px]", floor === null ? "bg-white text-black" : "bg-white/[0.06]")}>All floors</button>
            {selB.floors.map((f: any) => <button key={f.level} onClick={() => setFloor(f.level)} className={cn("rounded-full px-2.5 py-1 text-[11.5px]", floor === f.level ? "bg-white text-black" : "bg-white/[0.06]")}>L{f.level}</button>)}
          </div>
          {roomMeta && (
            <div className="mt-4 rounded-2xl bg-white/[0.04] p-3">
              <div className="flex items-center justify-between"><b className="text-[14px]">{roomMeta.name}</b><span className={cn("text-[10.5px] font-semibold rounded-full px-2 py-0.5", states[room!] === "free" ? "bg-[var(--green-soft)] text-[var(--green)]" : states[room!] === "affected" ? "bg-[var(--red-soft)] text-[var(--red)]" : "bg-[var(--accent-soft)] text-[var(--accent)]")}>{states[room!] === "free" ? "FREE" : states[room!]?.toUpperCase()}</span></div>
              <div className="faint text-[11.5px]">{roomMeta.type.replace("_", " ")} · {roomMeta.capacity} seats · level {roomMeta.level}</div>
              <div className="relative h-8 mt-3 rounded-lg bg-white/[0.04] overflow-hidden">
                {roomInfo?.sessions.map((s: any, i: number) => (
                  <div key={i} title={`${s.time || hm(s.s) + "-" + hm(s.e)} ${s.module}`} className="absolute inset-y-1 rounded-md"
                    style={{ left: `${((s.s - 480) / 780) * 100}%`, width: `${((s.e - s.s) / 780) * 100}%`, background: s.affected ? "var(--red)" : s.pending || s.moved ? "var(--green)" : "linear-gradient(90deg,#8b7cff,#4f8dff)" }} />
                ))}
                <div className="absolute inset-y-0 w-px bg-white" style={{ left: `${((t - 480) / 780) * 100}%` }} />
              </div>
              <div className="flex justify-between faint text-[10px] mt-1"><span>08:00</span><span>14:30</span><span>21:00</span></div>
              <div className="mt-2 space-y-1">
                {roomInfo?.sessions.length ? roomInfo.sessions.map((s: any, i: number) => (
                  <div key={i} className="text-[12px] flex gap-2"><span className="mono faint w-[78px] shrink-0">{hm(s.s)}–{hm(s.e)}</span><span className="truncate">{s.module}</span>{s.pending && <span className="text-[var(--green)] text-[10px]">proposed</span>}</div>
                )) : <div className="muted text-[12px]">No classes today.</div>}
              </div>
            </div>
          )}
        </div>
      )}

      {/* bottom: day + time */}
      <div className="absolute inset-x-0 bottom-5 flex justify-center px-4 md:pl-[264px]">
        <div className="glass-strong rounded-[22px] px-4 py-3 w-full max-w-[860px]">
          <div className="flex items-center gap-1.5 overflow-x-auto pb-2">
            {layout.dates.map((d: string) => (
              <button key={d} onClick={() => setDate(d)} className={cn("shrink-0 rounded-full px-3 py-1 text-[12px] transition", date === d ? "bg-white text-black font-medium" : "bg-white/[0.05] text-white/70 hover:bg-white/[0.1]")}>{fmtDate(d, { weekday: "short", day: "numeric", month: "short" })}</button>
            ))}
          </div>
          <div className="flex items-center gap-3">
            <button onClick={() => setPlaying((x) => !x)} className="h-9 w-9 shrink-0 rounded-full btn-gradient grid place-items-center">{playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}</button>
            <div className="mono text-[15px] tabular-nums w-[52px]">{hm(t)}</div>
            <input type="range" min={8 * 60} max={21 * 60} step={5} value={t} onChange={(e) => setT(+e.target.value)} className="flex-1 accent-[#8b7cff]" disabled={mode === "week"} />
            <div className="hidden md:flex items-center gap-3 text-[11px] faint">
              {mode === "live" ? (
                <>
                  <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: "#7a67ff" }} />in use</span>
                  <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm bg-[#30303d]" />free</span>
                  <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm bg-[var(--red)]" />affected</span>
                  <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm bg-[var(--green)]" />moved here</span>
                </>
              ) : (
                <span className="flex items-center gap-1.5">low <span className="h-2.5 w-24 rounded-full" style={{ background: "linear-gradient(90deg,#1c1f3a,#3b3fae,#7a5cff,#d24dff,#ffb24d)" }} /> high</span>
              )}
            </div>
          </div>
        </div>
      </div>
      <div className="absolute left-5 md:left-[284px] bottom-32 text-[10.5px] faint max-w-[260px]">{layout.note} Drag to orbit · scroll to zoom · click a building to open its floors.</div>
    </div>
  );
}
