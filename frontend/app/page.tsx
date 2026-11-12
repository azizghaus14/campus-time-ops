"use client";
import { ArrowUp, Box, CalendarClock, ClipboardCheck, Mic, Sparkles, TriangleAlert, UserRoundCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { CardAction, RenderCard } from "@/components/assistant/cards";
import { Aurora, ComposerGlow, Stardust } from "@/components/fx";
import { Orb, OrbState, stateFor } from "@/components/orb";
import { Ring, SegBar } from "@/components/viz";
import { post } from "@/lib/api";
import { cn, fmtDate, num } from "@/lib/format";
import { Session, useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

type Msg = { id: number; from: "user" | "assistant"; text: string; cards?: any[]; pending?: boolean; orb?: OrbState };

function md(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((p, i) => (p.startsWith("**") ? <b key={i} className="text-white font-semibold">{p.slice(2, -2)}</b> : <span key={i}>{p}</span>));
}

function greeting(s: Session, now?: string) {
  const h = now ? parseInt(now.slice(11, 13)) : 9;
  const part = h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  if (s.role === "admin") return part;
  if (s.role === "lecturer") return `${part}, ${s.user}`;
  return `${part}, ${s.name.split(" ")[0]}`;
}

const PROMPT: Record<string, string> = {
  admin: "What happened? e.g. “Monday 16 Nov is now a public holiday”",
  lecturer: "Tell me what you need, e.g. “I'm sick tomorrow, sort out my classes”",
  student: "Ask about your timetable or attendance",
};

export default function Home() {
  const session = useSession();
  if (!session) return null;
  return <Assistant session={session} />;
}

function Assistant({ session }: { session: Session }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [ctx, setCtx] = useState<any>({});
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const { data: sug } = useApi<any>("/assistant/suggestions");
  const { data: health } = useApi<any>("/health");
  const endRef = useRef<HTMLDivElement>(null);
  const idRef = useRef(1);
  const active = msgs.length > 0;

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs]);

  const send: CardAction = async (text, opts) => {
    const t = text.trim();
    if (!t || busy) return;
    const uid = idRef.current++, aid = idRef.current++;
    setInput("");
    if (opts?.inject) {
      const p = opts.inject;
      const can = session.role === "admin" || (session.role === "lecturer" && p.booking?.lecturer_ids?.includes(session.user));
      setMsgs((m) => [...m, { id: uid, from: "user", text: t }, {
        id: aid, from: "assistant", text: `Drafted the booking for **${p.summary.label}**. Approve it and I'll create the calendar invites and a Gmail draft.`,
        cards: [{ type: "proposal", id: p.id, version: 1, kind: p.kind, title: p.title, status: p.status, summary: p.summary, booking: p.booking, can_approve: can, citations: p.citations, moves: [] }],
      }]);
      setCtx({ proposal_id: p.id });
      return;
    }
    setMsgs((m) => [...m, { id: uid, from: "user", text: t }, { id: aid, from: "assistant", text: "", pending: true, orb: stateFor(t) }]);
    setBusy(true);
    try {
      const r = await post<any>("/assistant", { message: t, context: ctx });
      setCtx(r.context || {});
      setMsgs((m) => m.map((x) => (x.id === aid ? { id: aid, from: "assistant", text: r.reply, cards: r.cards, orb: "breathing" } : x)));
    } catch (e: any) {
      setMsgs((m) => m.map((x) => (x.id === aid ? { id: aid, from: "assistant", text: `Something went wrong: ${e.message || e}` } : x)));
    } finally {
      setBusy(false);
    }
  };

  const composer = (
    <div className="composer-wrap">
      <ComposerGlow soft={active} />
    <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="liquid w-full">
      <div className="relative flex items-end gap-2 p-2.5 pl-3.5">
        <span className="self-center pl-0.5"><Orb state={busy ? "solving" : input ? "listening" : "working"} size={30} tint="violet" /></span>
        <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={active ? 1 : 2}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
          placeholder={PROMPT[session.role]} aria-label="Message the assistant"
          className="flex-1 resize-none bg-transparent outline-none text-[16px] leading-6 py-2.5 placeholder:text-white/40" />
        <button type="button" title="Voice input (not in this prototype)" className="h-10 w-10 rounded-full grid place-items-center text-white/40 hover:text-white hover:bg-white/[0.06]"><Mic className="h-[18px] w-[18px]" /></button>
        <button type="submit" aria-label="Send" disabled={!input.trim() || busy} className="h-10 w-10 rounded-full grid place-items-center btn-gradient disabled:opacity-40 disabled:shadow-none transition"><ArrowUp className="h-[18px] w-[18px]" /></button>
      </div>
      <span className="edge-light" />
    </form>
    </div>
  );

  if (!active) {
    return (
      <section className="relative -mx-4 md:-ml-[260px] md:-mr-8 -mt-[88px] pt-14 md:pl-[260px] overflow-hidden min-h-screen flex flex-col">
        <div className="absolute inset-x-0 bottom-0 h-[72%]"><Aurora /></div>
        <Stardust density={1.3} />
        <div className="relative flex-1 flex flex-col items-center justify-center px-5 pt-14 pb-8">
          <div className="mb-5"><Orb state={input ? "listening" : "working"} size={104} tint="violet" halo /></div>
          <h1 className="text-center text-[40px] md:text-[60px] font-semibold tracking-[-0.04em] leading-[1.03]"><span className="text-gradient">{greeting(session, health?.now)}</span></h1>
          <p className="text-center muted mt-3 text-[17px] max-w-xl">
            {session.role === "student" ? "Your timetable, changes and attendance. Just ask." : "Describe what happened in plain words. I'll work out the impact, draft a clash-free plan and wait for your approval."}
          </p>
          <div className="w-full max-w-[760px] mt-10">{composer}</div>
          <div className="flex flex-wrap justify-center gap-2 mt-5 max-w-[860px]">
            {(sug?.suggestions || []).map((s: string) => (
              <button key={s} onClick={() => send(s)} className="rounded-full border border-white/10 bg-white/[0.05] backdrop-blur px-3.5 py-1.5 text-[13px] text-white/80 hover:bg-white/[0.1] hover:text-white transition">{s}</button>
            ))}
          </div>
        </div>
        <div className="relative px-4 md:px-8 pb-8"><Glance session={session} /></div>
      </section>
    );
  }

  return (
    <div className="max-w-[820px] mx-auto pb-48">
      <div className="space-y-6">
        {msgs.map((m) => (
          <div key={m.id} className={cn("rise", m.from === "user" ? "flex justify-end" : "")}>
            {m.from === "user" ? (
              <div className="max-w-[80%] rounded-[22px] rounded-br-md bg-white/[0.08] border border-white/[0.06] px-4 py-2.5 text-[15px]">{m.text}</div>
            ) : (
              <div className="flex gap-3">
                <div className="shrink-0 -mt-0.5"><Orb state={m.pending ? m.orb || "searching" : "working"} size={36} tint={m.pending ? "blue" : "violet"} halo={m.pending} /></div>
                <div className="min-w-0 flex-1 space-y-3">
                  {m.pending ? (
                    <div className="text-[14px] pt-2"><span className="shimmer">{m.orb === "solving" ? "Reading the live timetable and running the solver…" : m.orb === "connecting" ? "Applying the approved plan…" : m.orb === "weaving" ? "Finding a time when everyone is free…" : "Looking that up…"}</span></div>
                  ) : (
                    <div className="text-[15px] leading-relaxed text-white/85">{md(m.text)}</div>
                  )}
                  {m.cards?.map((c, i) => <RenderCard key={i} c={c} act={send} />)}
                </div>
              </div>
            )}
          </div>
        ))}
        <div ref={endRef} style={{ scrollMarginBottom: 230 }} />
      </div>
      <div className="fixed bottom-0 left-0 right-0 md:pl-[260px] z-30 pointer-events-none">
        <div className="relative h-[200px]">
          <div className="absolute inset-0 overflow-hidden">
            <div className="absolute inset-x-0 -bottom-16 h-[260px] opacity-80"><Aurora /></div>
            <Stardust density={0.5} />
          </div>
          <div className="absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-[var(--bg)] to-transparent" />
          <div className="absolute inset-x-0 bottom-6 px-4 pointer-events-auto">
            <div className="max-w-[820px] mx-auto">
              {composer}
              <div className="flex justify-between mt-2 px-2 text-[11px] faint">
                <span>Plans are drafts until approved · {session.role === "student" ? "read-only" : "Calendar · Gmail drafts · change log"}</span>
                <button onClick={() => { setMsgs([]); setCtx({}); }} className="hover:text-white">New conversation</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function GlanceCard({ title, icon: Icon, href, children }: { title: string; icon: any; href?: string; children: React.ReactNode }) {
  const body = (
    <div className="panel h-full p-5 hover:border-white/15 transition">
      <div className="flex items-center gap-2 text-[12px] muted font-medium"><Icon className="h-4 w-4 text-[var(--accent)]" /> {title}</div>
      <div className="mt-3">{children}</div>
    </div>
  );
  return href ? <Link href={href} className="block h-full">{body}</Link> : body;
}

function Glance({ session }: { session: Session }) {
  const { data: me } = useApi<any>("/me");
  const { data: ov } = useApi<any>(session.role === "admin" ? "/overview" : null);
  if (session.role === "admin") {
    if (!ov) return null;
    const k = ov.kpis;
    const max = Math.max(...ov.week_sessions_per_day.map((d: any) => d.sessions), 1);
    return (
      <div className="grid md:grid-cols-4 gap-3 max-w-[1200px] mx-auto">
        <GlanceCard title="Today on campus" icon={CalendarClock} href="/campus">
          <div className="text-[34px] font-semibold tracking-tight leading-none tabular-nums">{num(ov.today_sessions)}</div>
          <div className="faint text-[12px] mt-1">physical sessions · ~{num(ov.today_students)} students</div>
          <div className="flex items-end gap-1.5 h-12 mt-3">
            {ov.week_sessions_per_day.map((d: any) => <div key={d.date} className="flex-1 rounded-t-md bg-gradient-to-t from-violet-500/40 to-blue-400/80" style={{ height: `${Math.max(4, (d.sessions / max) * 100)}%` }} title={`${d.day} ${d.sessions}`} />)}
          </div>
        </GlanceCard>
        <GlanceCard title="Waiting for approval" icon={ClipboardCheck} href="/proposals">
          <div className="text-[34px] font-semibold tracking-tight leading-none tabular-nums text-[var(--amber)]">{k.pending_approvals}</div>
          <div className="faint text-[12px] mt-1">draft plans</div>
          <div className="mt-3 space-y-1">{ov.pending_approvals.slice(0, 2).map((p: any) => <div key={p.id} className="text-[12px] truncate text-white/75">{p.title}</div>)}</div>
        </GlanceCard>
        <GlanceCard title="Re-planned so far" icon={Sparkles} href="/audit">
          <div className="text-[34px] font-semibold tracking-tight leading-none tabular-nums text-[var(--green)]">{num(k.sessions_replanned)}</div>
          <div className="faint text-[12px] mt-1">{k.substitutes_found} by substitute · median {k.median_time_to_replan_s ?? "–"}s</div>
          <SegBar className="mt-4" parts={[{ value: k.substitutes_found, color: "var(--violet)" }, { value: Math.max(0, k.sessions_replanned - k.substitutes_found), color: "var(--green)" }]} />
        </GlanceCard>
        <GlanceCard title="Attendance risk" icon={UserRoundCheck} href="/attendance">
          <div className="text-[34px] font-semibold tracking-tight leading-none tabular-nums text-[var(--red)]">{num(k.students_below_threshold)}</div>
          <div className="faint text-[12px] mt-1">students below 80% (synthetic)</div>
          <div className="mt-3 flex items-center gap-2"><Box className="h-3.5 w-3.5 text-[var(--accent)]" /><span className="text-[12px] text-[var(--accent)]">Open the 3D campus →</span></div>
        </GlanceCard>
      </div>
    );
  }
  if (!me) return null;
  if (session.role === "student") {
    const f = me.attendance;
    const thr = Math.round(f.threshold * 100);
    return (
      <div className="grid md:grid-cols-3 gap-3 max-w-[1100px] mx-auto">
        <GlanceCard title="Attendance" icon={UserRoundCheck} href="/attendance">
          <div className="flex items-center gap-4">
            <Ring value={f.current_percent || 0} marker={thr} size={96} stroke={9} color={f.max_more_absences < 0 ? "url(#ringRed)" : f.max_more_absences <= 2 ? "url(#ringAmber)" : "url(#ringGreen)"} label={`${Math.round(f.current_percent)}%`} />
            <div><div className="text-[22px] font-semibold leading-tight">{f.max_more_absences < 0 ? "At risk" : `${f.max_more_absences} more`}</div><div className="faint text-[12px]">{f.max_more_absences < 0 ? f.binding_module : "classes you can miss"}</div></div>
          </div>
        </GlanceCard>
        <GlanceCard title="Coming up" icon={CalendarClock} href="/week">
          <div className="space-y-1.5">{me.schedule.slice(0, 4).map((s: any) => <div key={s.id} className="flex gap-2 text-[12.5px]"><span className="mono faint w-[86px] shrink-0">{fmtDate(s.date, { weekday: "short" })} {s.time.slice(0, 5)}</span><span className="truncate">{s.module_name}</span></div>)}</div>
        </GlanceCard>
        <GlanceCard title="Changes to my classes" icon={TriangleAlert} href="/week">
          {me.changes.length === 0 ? <div className="muted text-[13px]">No changes. Everything runs as planned.</div> : (
            <div className="space-y-1.5">{me.changes.slice(0, 3).map((s: any) => <div key={s.id} className="text-[12.5px]"><span className="text-[var(--green)] font-semibold">MOVED</span> {s.module_name} → {fmtDate(s.date)} {s.time.slice(0, 5)} {s.room}</div>)}</div>
          )}
        </GlanceCard>
      </div>
    );
  }
  const days = Array.from(new Set(me.schedule.map((s: any) => s.date))).slice(0, 6) as string[];
  return (
    <div className="grid md:grid-cols-3 gap-3 max-w-[1100px] mx-auto">
      <GlanceCard title="Your next sessions" icon={CalendarClock} href="/week">
        <div className="space-y-1.5">{me.schedule.slice(0, 4).map((s: any) => <div key={s.id} className="flex gap-2 text-[12.5px]"><span className="mono faint w-[86px] shrink-0">{fmtDate(s.date, { weekday: "short" })} {s.time.slice(0, 5)}</span><span className="truncate">{s.module_name}</span></div>)}</div>
      </GlanceCard>
      <GlanceCard title="Teaching days ahead" icon={Sparkles} href="/week">
        <div className="flex items-end gap-1.5 h-16">{days.map((d) => { const n = me.schedule.filter((s: any) => s.date === d).length; return <div key={d} className="flex-1 flex flex-col items-center gap-1"><div className="w-full rounded-t-md bg-gradient-to-t from-violet-500/40 to-blue-400/80" style={{ height: `${Math.min(48, n * 16)}px` }} /><span className="faint text-[10px]">{fmtDate(d, { weekday: "short" })}</span></div>; })}</div>
      </GlanceCard>
      <GlanceCard title="My requests" icon={ClipboardCheck} href="/proposals">
        {me.proposals.length === 0 ? <div className="muted text-[13px]">No requests yet. Try “I&apos;m sick tomorrow”.</div> : (
          <div className="space-y-1.5">{me.proposals.slice(0, 3).map((p: any) => <div key={p.id} className="flex justify-between gap-2 text-[12.5px]"><span className="truncate">{p.title}</span><span className="faint shrink-0">{p.status}</span></div>)}</div>
        )}
      </GlanceCard>
    </div>
  );
}
