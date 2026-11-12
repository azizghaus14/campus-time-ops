"use client";
// The demo's main visual: affected sessions appear red on a week grid (rows = time bands, columns = days);
// while the solver runs a scan line sweeps; then sessions turn green (violet = substitute, amber = online) as they're placed.
import { useEffect, useMemo, useState } from "react";

import { cn, fmtDate } from "@/lib/format";

const BANDS = [
  { label: "08:30", from: 0, to: 10 * 60 + 45 },
  { label: "10:45", from: 10 * 60 + 45, to: 13 * 60 + 30 },
  { label: "13:30", from: 13 * 60 + 30, to: 15 * 60 + 45 },
  { label: "15:45", from: 15 * 60 + 45, to: 18 * 60 + 45 },
  { label: "18:45", from: 18 * 60 + 45, to: 24 * 60 },
];

function band(iso: string) {
  const m = parseInt(iso.slice(11, 13)) * 60 + parseInt(iso.slice(14, 16));
  return BANDS.findIndex((b) => m >= b.from && m < b.to);
}

type Dot = { id: string; title: string };

export default function ReplanGrid({ affected, moves, unresolved, solving, onDone }: {
  affected: any[]; moves: any[] | null; unresolved: any[] | null; solving: boolean; onDone?: () => void;
}) {
  const [revealed, setRevealed] = useState(0);
  const total = moves?.length || 0;

  useEffect(() => {
    setRevealed(0);
    if (!moves || !moves.length) return;
    const step = Math.max(1, Math.ceil(moves.length / 160));
    const ms = Math.max(6, Math.min(140, 2800 / Math.ceil(moves.length / step)));
    let n = 0;
    const t = setInterval(() => {
      n = Math.min(moves.length, n + step);
      setRevealed(n);
      if (n >= moves.length) {
        clearInterval(t);
        onDone?.();
      }
    }, ms);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moves]);

  const order = useMemo(() => (moves ? [...moves].sort((a, b) => (a.school + a.from.start).localeCompare(b.school + b.from.start)) : []), [moves]);
  const placed = useMemo(() => new Map(order.slice(0, revealed).map((m) => [m.session_id, m])), [order, revealed]);
  const unresolvedIds = useMemo(() => new Set((unresolved || []).map((u: any) => u.session?.id)), [unresolved]);

  const days = useMemo(() => {
    const set = new Set<string>(affected.map((s) => s.date));
    (moves || []).forEach((m) => set.add(m.to.date));
    const sorted = [...set].sort();
    if (!sorted.length) return [];
    const out: string[] = [];
    const d = new Date(sorted[0] + "T12:00:00+08:00");
    const end = new Date(sorted[sorted.length - 1] + "T12:00:00+08:00");
    while (d <= end) {
      const iso = new Date(d.getTime() + 8 * 3600e3).toISOString().slice(0, 10);
      const wd = new Date(iso + "T12:00:00+08:00").getUTCDay();
      if (wd !== 0 && wd !== 6) out.push(iso);
      d.setUTCDate(d.getUTCDate() + 1);
    }
    return out.slice(0, 12);
  }, [affected, moves]);

  const cells = useMemo(() => {
    const c: Record<string, { red: Dot[]; gone: Dot[]; green: Dot[]; violet: Dot[]; amber: Dot[] }> = {};
    const cell = (d: string, b: number) => (c[`${d}|${b}`] ||= { red: [], gone: [], green: [], violet: [], amber: [] });
    for (const s of affected) {
      const m = placed.get(s.id);
      const title = `${s.module_name} · ${s.lecturer_id} · ${s.time} ${s.room}`;
      if (m?.type === "SUBSTITUTE") cell(s.date, band(s.start)).violet.push({ id: s.id, title: `${title} → taught by ${m.substitute}` });
      else if (m) cell(s.date, band(s.start)).gone.push({ id: s.id, title });
      else cell(s.date, band(s.start)).red.push({ id: s.id, title: unresolvedIds.has(s.id) && revealed >= total ? `${title} (unresolved)` : title });
    }
    for (const m of order.slice(0, revealed)) {
      if (m.type === "SUBSTITUTE") continue;
      const t = `${m.module_name} · ${m.from.label} ${m.from.room} → ${m.to.label} ${m.to.room}`;
      (m.type === "ONLINE" ? cell(m.to.date, band(m.to.start)).amber : cell(m.to.date, band(m.to.start)).green).push({ id: m.session_id, title: t });
    }
    return c;
  }, [affected, placed, order, revealed, unresolvedIds, total]);

  const dense = affected.length > 120;
  const dot = dense ? "h-[6px] w-[6px]" : "h-3 w-3";

  return (
    <div className="relative overflow-x-auto rounded-xl border border-[var(--border)]">
      {solving && <div className="pointer-events-none absolute inset-y-0 left-0 w-1/4 bg-gradient-to-r from-transparent via-[var(--accent)]/15 to-transparent scanline z-10" />}
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            <th className="w-14 p-2 text-left muted font-medium">Slot</th>
            {days.map((d) => (
              <th key={d} className="p-2 text-left font-medium muted min-w-[92px]">{fmtDate(d, { weekday: "short", day: "2-digit", month: "short" })}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {BANDS.map((b, bi) => (
            <tr key={b.label} className="border-t border-[var(--border)]">
              <td className="p-2 muted mono align-top">{b.label}</td>
              {days.map((d) => {
                const c = cells[`${d}|${bi}`];
                return (
                  <td key={d} className="p-1.5 align-top border-l border-[var(--border)]">
                    <div className="flex flex-wrap gap-[2px] min-h-[18px]">
                      {c?.red.map((x) => <span key={"r" + x.id} title={x.title} className={cn(dot, "rounded-full bg-[var(--red)]", !moves && "dot-pulse")} />)}
                      {c?.gone.map((x) => <span key={"g" + x.id} title={x.title + " (moved)"} className={cn(dot, "rounded-full border border-[var(--red)]/50 opacity-40")} />)}
                      {c?.violet.map((x) => <span key={"v" + x.id} title={x.title} className={cn(dot, "rounded-full bg-[var(--violet)] dot-pop")} />)}
                      {c?.green.map((x) => <span key={"n" + x.id} title={x.title} className={cn(dot, "rounded-full bg-[var(--green)] dot-pop")} />)}
                      {c?.amber.map((x) => <span key={"a" + x.id} title={x.title} className={cn(dot, "rounded-full bg-[var(--amber)] dot-pop")} />)}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex flex-wrap items-center gap-4 border-t border-[var(--border)] px-3 py-2 text-[11px] muted">
        <Legend c="var(--red)" t="affected / unresolved" /><Legend c="var(--green)" t="placed in a room" /><Legend c="var(--violet)" t="substitute lecturer" />
        <Legend c="var(--amber)" t="online fallback" /><span className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full border border-[var(--red)]/50 opacity-50" />vacated slot</span>
        {moves && <span className="ml-auto tabular-nums text-[var(--text)]">placed {revealed} / {affected.length}</span>}
      </div>
    </div>
  );
}

function Legend({ c, t }: { c: string; t: string }) {
  return <span className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full" style={{ background: c }} />{t}</span>;
}
