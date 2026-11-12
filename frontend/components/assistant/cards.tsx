"use client";
import { ArrowRight, CalendarCheck, Check, CheckCircle2, ExternalLink, FileText, Mail, MapPin, Users, Wand2, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Ring, SegBar, Spark, TYPE_META } from "@/components/viz";
import { post } from "@/lib/api";
import { cn, fmtDate, num } from "@/lib/format";

export type CardAction = (text: string, opts?: { silent?: boolean; inject?: any }) => void;

function Shell({ children, className, glow }: { children: React.ReactNode; className?: string; glow?: boolean }) {
  return (
    <div className={cn("panel rise !rounded-[22px] overflow-hidden", glow && "shadow-[0_0_0_1px_rgba(139,124,255,0.25),0_30px_80px_-30px_rgba(139,124,255,0.55)]", className)}>
      {children}
    </div>
  );
}

const day = (iso: string) => fmtDate(iso.slice(0, 10), { weekday: "short", day: "2-digit", month: "short" });
const tm = (iso: string) => iso.slice(11, 16);

export function ImpactCard({ c }: { c: any }) {
  const i = c.impact;
  const kind = c.disruption_type === "HOLIDAY" ? "Holiday" : c.disruption_type === "ROOM_UNAVAILABLE" ? "Room closed" : "Lecturer unavailable";
  return (
    <Shell>
      <div className="p-5">
        <div className="flex items-center gap-2 text-[11px] font-semibold tracking-wide uppercase text-[var(--red)]"><span className="h-1.5 w-1.5 rounded-full bg-[var(--red)] animate-pulse" /> Impact · {kind}</div>
        <div className="grid grid-cols-3 gap-3 mt-4">
          {[["Sessions", i.sessions], ["Intake groups", i.intake_groups], ["Students", `~${num(i.students)}`]].map(([l, v]) => (
            <div key={l as string}>
              <div className="text-[30px] font-semibold tabular-nums tracking-tight leading-none">{v}</div>
              <div className="faint text-[12px] mt-1.5">{l}</div>
            </div>
          ))}
        </div>
        {c.sessions?.length > 0 && c.disruption_type !== "HOLIDAY" && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {c.sessions.map((s: any, k: number) => (
              <span key={k} className="rounded-full bg-[var(--red-soft)] text-[var(--red)] px-2.5 py-1 text-[11.5px]">{s.module} · {fmtDate(s.date, { weekday: "short" })} {s.time.slice(0, 5)}</span>
            ))}
          </div>
        )}
      </div>
    </Shell>
  );
}

export function ProposalCard({ c, act }: { c: any; act: CardAction }) {
  const s = c.summary || {};
  const [busy, setBusy] = useState(false);
  const isSlot = c.kind === "SLOT_BOOKING";
  const parts = isSlot ? [] : [
    { value: s.substituted || 0, color: TYPE_META.SUBSTITUTE.color, label: "Substitute" },
    { value: s.rescheduled || 0, color: TYPE_META.RESCHEDULE.color, label: "Rescheduled" },
    { value: s.placed_online || 0, color: TYPE_META.ONLINE.color, label: "Online" },
    { value: s.unresolved || 0, color: TYPE_META.UNRESOLVED.color, label: "Needs decision" },
  ];
  const draft = c.status === "DRAFT";
  return (
    <Shell glow={draft}>
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-[11px] font-semibold tracking-wide uppercase">
              <Wand2 className="h-3.5 w-3.5 text-[var(--accent)]" />
              <span className="text-[var(--accent)]">{isSlot ? "Booking draft" : "Plan"} v{c.version}</span>
              <span className={cn("rounded-full px-2 py-0.5 text-[10px]", draft ? "bg-[var(--amber-soft)] text-[var(--amber)]" : c.status === "EXECUTED" ? "bg-[var(--green-soft)] text-[var(--green)]" : "bg-white/[0.06] muted")}>{draft ? "Awaiting approval" : c.status}</span>
            </div>
            <div className="mt-1.5 font-semibold text-[16px] tracking-tight">{c.title}</div>
          </div>
          {!isSlot && c.stats?.total_s != null && <div className="text-right"><div className="text-[18px] font-semibold tabular-nums">{c.stats.total_s}s</div><div className="faint text-[10.5px]">solver · clash-free</div></div>}
        </div>

        {!isSlot && (
          <div className="mt-4">
            <SegBar parts={parts} height={10} />
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2.5">
              {parts.map((p) => (
                <span key={p.label} className="flex items-center gap-1.5 text-[12px]"><span className="h-2 w-2 rounded-full" style={{ background: p.color }} /><b className="tabular-nums">{p.value}</b><span className="muted">{p.label}</span></span>
              ))}
            </div>
          </div>
        )}

        {isSlot && c.booking && (
          <div className="mt-4 flex items-center gap-3 rounded-2xl bg-white/[0.04] p-3.5">
            <div className="h-11 w-11 rounded-xl btn-gradient grid place-items-center"><CalendarCheck className="h-5 w-5" /></div>
            <div>
              <div className="font-medium">{day(c.booking.start)} · {tm(c.booking.start)}–{tm(c.booking.end)}</div>
              <div className="muted text-[12.5px]">{c.booking.room} · {c.booking.lecturer_ids.join(", ")}{c.booking.groups.length ? ` · ${c.booking.groups.length} group(s)` : ""}</div>
            </div>
          </div>
        )}

        {c.moves?.length > 0 && (
          <div className="mt-4 space-y-1.5">
            {c.moves.map((m: any) => {
              const meta = TYPE_META[m.type];
              return (
                <div key={m.session_id} className="group rounded-2xl bg-white/[0.03] hover:bg-white/[0.05] border border-white/[0.04] px-3.5 py-3 transition" title={m.why}>
                  <div className="flex items-center gap-3">
                    <span className="h-8 w-1 rounded-full shrink-0" style={{ background: meta.color }} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-[13.5px] truncate">{m.module}</span>
                        <span className="rounded-full px-2 py-[1px] text-[10px] font-semibold" style={{ background: meta.soft, color: meta.color }}>{meta.label}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-2 text-[12px] muted mt-0.5">
                        <span>{day(m.from.start)} {tm(m.from.start)} · {m.from.room}</span>
                        <ArrowRight className="h-3 w-3 opacity-60" />
                        {m.type === "SUBSTITUTE" ? (
                          <span className="text-white/90">same slot, taught by <b style={{ color: meta.color }}>{m.substitute}</b></span>
                        ) : (
                          <span className="text-white/90">{day(m.to.start)} {tm(m.to.start)} · {m.to.room === "ONLINE" ? "Online" : m.to.room}</span>
                        )}
                      </div>
                    </div>
                    <div className="text-right shrink-0 hidden sm:block"><div className="text-[12px] tabular-nums">{m.students}</div><div className="faint text-[10px]">students</div></div>
                  </div>
                  <div className="hidden group-hover:flex flex-wrap gap-1 mt-2 pl-4">{m.rules.map((r: string) => <span key={r} className="rounded-full bg-white/[0.05] px-1.5 py-[1px] text-[10px] muted">{r}</span>)}</div>
                </div>
              );
            })}
            {c.more_moves > 0 && (
              <div className="faint text-[12px] px-1 pt-1">+ {num(c.more_moves)} more moves{s.by_school ? " — summary by school below" : ""}</div>
            )}
          </div>
        )}

        {s.by_school && (
          <div className="mt-4 grid grid-cols-2 md:grid-cols-3 gap-2">
            {s.by_school.slice(0, 6).map((r: any) => (
              <div key={r.school} className="rounded-xl bg-white/[0.03] px-3 py-2">
                <div className="flex justify-between text-[12px]"><b>{r.school}</b><span className="muted tabular-nums">{r.sessions}</span></div>
                <SegBar className="mt-1.5" height={5} parts={[{ value: r.physical, color: "var(--green)" }, { value: r.online, color: "var(--amber)" }, { value: r.unresolved, color: "var(--red)" }]} />
              </div>
            ))}
          </div>
        )}

        {c.unresolved?.length > 0 && (
          <div className="mt-3 space-y-1">{c.unresolved.map((u: any, k: number) => <div key={k} className="text-[12px] text-[var(--red)]">● {u.module} {u.when} — {u.reason}</div>)}</div>
        )}

        {draft && (
          <div className="mt-5 flex flex-wrap items-center gap-2">
            {c.can_approve ? (
              <button disabled={busy} onClick={() => { setBusy(true); act("Approve"); }}
                className="btn-gradient rounded-full h-10 px-5 text-[13.5px] font-medium inline-flex items-center gap-2 disabled:opacity-60">
                <Check className="h-4 w-4" /> Approve &amp; apply
              </button>
            ) : (
              <span className="rounded-full bg-white/[0.05] px-3.5 h-10 inline-flex items-center text-[12.5px] muted">Sent to the timetabling office for approval</span>
            )}
            {!isSlot && c.can_approve && c.moves?.some((m: any) => m.type !== "SUBSTITUTE") && (
              <button onClick={() => act("Move it to the afternoon")} className="rounded-full h-10 px-4 text-[13px] border border-white/10 bg-white/[0.04] hover:bg-white/[0.08]">Prefer afternoon</button>
            )}
            {!isSlot && c.can_approve && c.moves?.some((m: any) => m.type === "SUBSTITUTE") && (
              <button onClick={() => act("Don't use a substitute")} className="rounded-full h-10 px-4 text-[13px] border border-white/10 bg-white/[0.04] hover:bg-white/[0.08]">No substitute</button>
            )}
            {c.can_approve && <button onClick={() => act("Reject")} className="rounded-full h-10 w-10 grid place-items-center border border-white/10 bg-white/[0.04] hover:bg-white/[0.08]" title="Reject"><X className="h-4 w-4" /></button>}
            <Link href={`/proposals/${c.id}`} className="ml-auto text-[12.5px] text-[var(--accent)] inline-flex items-center gap-1">Full plan <ExternalLink className="h-3 w-3" /></Link>
          </div>
        )}
        {draft && <div className="faint text-[11px] mt-3">Nothing changes until a person approves · rules: {c.citations?.slice(0, 5).map((x: any) => x.id).join(", ")}</div>}
      </div>
    </Shell>
  );
}

export function ExecutedCard({ c }: { c: any }) {
  const a = c.actions || {};
  const tiles = [
    { icon: CalendarCheck, n: a.calendar_events || 0, l: "Calendar events", href: c.links?.calendar },
    { icon: Mail, n: a.gmail_drafts || 0, l: "Gmail drafts", href: c.links?.drafts },
    { icon: FileText, n: a.changelog_entries || 0, l: "Change-log entry", href: c.links?.changelog },
  ];
  return (
    <Shell className="!border-[var(--green)]/25">
      <div className="p-5">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-[var(--green-soft)] grid place-items-center"><CheckCircle2 className="h-5 w-5 text-[var(--green)]" /></div>
          <div><div className="font-semibold tracking-tight">Applied to the timetable</div><div className="muted text-[12px]">Drafts are waiting in Gmail for a person to send · logged in the audit trail</div></div>
        </div>
        <div className="grid grid-cols-3 gap-2 mt-4">
          {tiles.map((t) => (
            <a key={t.l} href={t.href || "#"} target="_blank" className="rounded-2xl bg-white/[0.04] hover:bg-white/[0.07] p-3 transition">
              <t.icon className="h-4 w-4 text-[var(--green)]" />
              <div className="text-[22px] font-semibold tabular-nums mt-1.5">{t.n}</div>
              <div className="faint text-[11px]">{t.l}</div>
            </a>
          ))}
        </div>
        {c.drafts?.length > 0 && (
          <div className="mt-3 space-y-1">{c.drafts.slice(0, 4).map((d: any, k: number) => (
            <a key={k} href={d.url} target="_blank" className="flex items-center gap-2 text-[12px] muted hover:text-white"><Mail className="h-3 w-3" /><span className="truncate">{d.subject}</span><span className="faint truncate">→ {d.to.join(", ")}</span></a>
          ))}</div>
        )}
      </div>
    </Shell>
  );
}

export function SlotsCard({ c, act }: { c: any; act: CardAction }) {
  const [busy, setBusy] = useState<string | null>(null);
  async function draft(o: any) {
    setBusy(o.start);
    try {
      const p = await post<any>("/slots/propose", { title: c.title, slot: o, groups: c.groups, lecturer_ids: c.lecturers, room: o.room, description: "Booked via the assistant" });
      act(`Draft invites for option #${o.rank}`, { inject: p });
    } finally {
      setBusy(null);
    }
  }
  return (
    <Shell>
      <div className="p-5">
        <div className="text-[11px] font-semibold tracking-wide uppercase text-[var(--accent)]">Top 3 slots</div>
        <div className="grid md:grid-cols-3 gap-2.5 mt-3">
          {c.options.map((o: any) => (
            <div key={o.start} className={cn("rounded-2xl p-4 border", o.rank === 1 ? "border-[var(--accent)]/40 bg-[var(--accent-soft)]" : "border-white/[0.06] bg-white/[0.03]")}>
              <div className="flex justify-between items-center"><span className="text-[11px] font-semibold text-[var(--accent)]">#{o.rank}{o.rank === 1 ? " · best" : ""}</span><span className="faint text-[10.5px]">{o.score}</span></div>
              <div className="text-[17px] font-semibold tracking-tight mt-1.5">{day(o.start)}</div>
              <div className="text-[14px] tabular-nums">{tm(o.start)}–{tm(o.end)}</div>
              <div className="muted text-[12px] mt-1 flex items-center gap-1"><MapPin className="h-3 w-3" /> {o.room}</div>
              {o.sub_slots && <div className="flex flex-wrap gap-1 mt-2">{o.sub_slots.map((x: any, i: number) => <span key={i} className="mono text-[10px] rounded-md bg-white/[0.06] px-1.5 py-0.5">{tm(x.start)}</span>)}</div>}
              <button disabled={!!busy} onClick={() => draft(o)} className="mt-3 w-full rounded-full h-9 text-[12.5px] font-medium btn-gradient disabled:opacity-60">{busy === o.start ? "Drafting…" : "Draft invites"}</button>
            </div>
          ))}
        </div>
      </div>
    </Shell>
  );
}

export function AttendanceCard({ c }: { c: any }) {
  const thr = Math.round(c.threshold * 100);
  const n = c.max_more_absences;
  const tone = n < 0 ? "url(#ringRed)" : n <= 2 ? "url(#ringAmber)" : "url(#ringGreen)";
  return (
    <Shell>
      <div className="p-5 flex flex-col sm:flex-row gap-5 items-center">
        <Ring value={c.current_percent || 0} marker={thr} size={132} stroke={11} color={tone} label={`${Math.round(c.current_percent)}%`} sub={`target ${thr}%`} />
        <div className="flex-1 min-w-0 w-full">
          <div className="muted text-[12.5px]">{n < 0 ? "Can no longer reach the target in" : "You can miss at most"}</div>
          <div className="text-[36px] font-semibold tracking-tight leading-tight">{n < 0 ? c.binding_module : <>{n} more class{n === 1 ? "" : "es"}</>}</div>
          {n >= 0 && c.binding_module && <div className="faint text-[12px]">in {c.binding_module} · {c.remaining_sessions} sessions left this term</div>}
          <div className="flex items-center gap-3 mt-3"><Spark data={c.weekly} w={120} h={30} threshold={thr} /><span className="faint text-[11px]">trend · {c.trend}</span></div>
          {c.next_class && <div className="mt-3 text-[12.5px] rounded-xl bg-white/[0.04] px-3 py-2">Next: <b>{c.next_class.module}</b> · {fmtDate(c.next_class.date)} {c.next_class.time.slice(0, 5)} · {c.next_class.room}</div>}
        </div>
      </div>
    </Shell>
  );
}

export function ScheduleCard({ c }: { c: any }) {
  const byDay: Record<string, any[]> = {};
  for (const s of c.sessions) (byDay[s.date] ||= []).push(s);
  return (
    <Shell>
      <div className="p-5">
        <div className="text-[11px] font-semibold tracking-wide uppercase text-[var(--accent)]">{c.title}</div>
        {c.sessions.length === 0 ? <div className="muted text-sm mt-3">No classes.</div> : (
          <div className="mt-3 space-y-3">
            {Object.entries(byDay).map(([d, ss]) => (
              <div key={d}>
                <div className="faint text-[11px] mb-1.5">{fmtDate(d, { weekday: "long", day: "numeric", month: "short" })}</div>
                <div className="space-y-1.5">
                  {ss.map((s) => (
                    <div key={s.id} className={cn("flex items-center gap-3 rounded-xl px-3 py-2", s.moved ? "bg-[var(--green-soft)]" : "bg-white/[0.03]")}>
                      <div className="mono text-[12px] w-[86px] shrink-0 tabular-nums">{s.time}</div>
                      <div className="min-w-0 flex-1"><div className="text-[13px] font-medium truncate">{s.module}</div><div className="faint text-[11px]">{s.room} · {s.lecturer} · {s.groups} group(s)</div></div>
                      {s.moved && <span className="text-[10px] font-semibold text-[var(--green)]">MOVED</span>}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Shell>
  );
}

export function RoomsCard({ c }: { c: any }) {
  return (
    <Shell>
      <div className="p-5">
        <div className="text-[11px] font-semibold tracking-wide uppercase text-[var(--green)]">{c.title}</div>
        <div className="flex flex-wrap gap-1.5 mt-3">
          {c.rooms.map((r: any) => (
            <span key={r.name} className="rounded-xl bg-[var(--green-soft)] px-2.5 py-1.5 text-[12px]"><b>{r.name}</b> <span className="muted inline-flex items-center gap-0.5"><Users className="h-3 w-3" />{r.capacity}</span></span>
          ))}
        </div>
        {c.count > c.rooms.length && <div className="faint text-[11px] mt-2">+ {c.count - c.rooms.length} more</div>}
      </div>
    </Shell>
  );
}

export function ErrorCard({ c }: { c: any }) {
  return <div className="rounded-2xl border border-[var(--red)]/25 bg-[var(--red-soft)] px-4 py-3 text-[13px] text-[var(--red)] rise">{c.message}</div>;
}

export function RenderCard({ c, act }: { c: any; act: CardAction }) {
  switch (c.type) {
    case "impact": return <ImpactCard c={c} />;
    case "proposal": return <ProposalCard c={c} act={act} />;
    case "executed": return <ExecutedCard c={c} />;
    case "slots": return <SlotsCard c={c} act={act} />;
    case "attendance": return <AttendanceCard c={c} />;
    case "schedule": return <ScheduleCard c={c} />;
    case "rooms": return <RoomsCard c={c} />;
    case "error": return <ErrorCard c={c} />;
    default: return null;
  }
}
