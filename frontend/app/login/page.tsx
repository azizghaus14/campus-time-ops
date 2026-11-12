"use client";
import { ArrowRight, Building2, GraduationCap, Presentation, Sparkles } from "lucide-react";
import { useState } from "react";

import { Aurora, Stardust } from "@/components/fx";
import { Orb } from "@/components/orb";
import { cn } from "@/lib/format";
import { Role, setSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

const ROLES: { role: Role; title: string; sub: string; icon: any; can: string[] }[] = [
  { role: "admin", title: "Timetabling Office", sub: "Run campus operations", icon: Building2,
    can: ["Re-plan disruptions campus-wide", "Approve every change", "3D campus, rooms & health"] },
  { role: "lecturer", title: "Lecturer", sub: "Your classes, sorted", icon: Presentation,
    can: ["“I'm sick tomorrow” → substitutes & reschedules", "Book vivas and make-ups", "See your week"] },
  { role: "student", title: "Student", sub: "Your timetable & attendance", icon: GraduationCap,
    can: ["What changed in my timetable", "How many classes can I miss", "Find a free study room"] },
];

export default function Login() {
  const { data } = useApi<any>("/personas");
  const [role, setRole] = useState<Role>("lecturer");
  const [pick, setPick] = useState<string>("");
  const people: any[] = data?.[role] || [];
  const chosen = people.find((p) => p.id === pick) || people[0];

  function go() {
    if (!chosen) return;
    setSession({ role, user: role === "admin" ? "ADMIN" : chosen.id, name: chosen.name });
    window.location.href = "/";
  }

  return (
    <div className="relative min-h-screen overflow-hidden flex flex-col items-center justify-center px-5 py-16">
      <div className="absolute inset-x-0 bottom-0 h-[70vh]"><Aurora /></div>
      <div className="absolute inset-0"><Stardust density={1.2} /></div>
      <div className="relative w-full max-w-[980px]">
        <div className="flex flex-col items-center mb-6 gap-5">
          <Orb state="connecting" size={112} tint="violet" halo />
          <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[12px] muted backdrop-blur">
            <Sparkles className="h-3.5 w-3.5 text-[var(--accent)]" /> APU Cloud Innovation Hackathon 2026
          </div>
        </div>
        <h1 className="text-center text-[44px] md:text-[64px] font-semibold tracking-[-0.04em] leading-[1.02]">
          <span className="text-gradient">Campus Time Ops</span>
        </h1>
        <p className="text-center muted mt-4 text-[17px]">AI that re-plans APU&apos;s live timetable — and a human approves every step.</p>

        <div className="grid md:grid-cols-3 gap-3 mt-12">
          {ROLES.map((r) => (
            <button key={r.role} onClick={() => { setRole(r.role); setPick(""); }}
              className={cn("text-left rounded-[22px] p-5 transition border", role === r.role ? "glass-strong border-[var(--accent)]/60 shadow-[0_0_0_1px_rgba(139,124,255,0.4),0_20px_60px_-20px_rgba(139,124,255,0.6)]" : "panel hover:border-white/20")}>
              <div className={cn("h-10 w-10 rounded-2xl grid place-items-center", role === r.role ? "btn-gradient" : "bg-white/[0.06]")}><r.icon className="h-5 w-5" /></div>
              <div className="mt-4 font-semibold text-[17px] tracking-tight">{r.title}</div>
              <div className="muted text-[13px]">{r.sub}</div>
              <ul className="mt-3 space-y-1.5">{r.can.map((c) => <li key={c} className="text-[12.5px] text-white/70 flex gap-2"><span className="mt-[7px] h-1 w-1 rounded-full bg-[var(--accent)] shrink-0" />{c}</li>)}</ul>
            </button>
          ))}
        </div>

        <div className="glass-strong rounded-[24px] mt-4 p-3 flex flex-col md:flex-row md:items-center gap-3">
          <div className="flex-1 flex gap-2 overflow-x-auto px-1">
            {people.map((p) => (
              <button key={p.id} onClick={() => setPick(p.id)}
                className={cn("shrink-0 rounded-2xl px-3.5 py-2 text-left border transition", (chosen?.id === p.id) ? "border-[var(--accent)]/60 bg-[var(--accent-soft)]" : "border-white/[0.06] bg-white/[0.03] hover:bg-white/[0.06]")}>
                <div className="text-[13px] font-medium whitespace-nowrap">{p.name}{role !== "admin" && <span className="faint"> · {p.id}</span>}</div>
                <div className="faint text-[11px] whitespace-nowrap max-w-[220px] truncate">{p.subtitle}</div>
              </button>
            ))}
            {!people.length && <div className="muted text-sm px-2 py-2">Loading personas…</div>}
          </div>
          <button onClick={go} disabled={!chosen} className="btn-gradient rounded-full h-11 px-6 text-[14px] font-medium inline-flex items-center justify-center gap-2 disabled:opacity-50">
            Continue as {ROLES.find((r) => r.role === role)?.title} <ArrowRight className="h-4 w-4" />
          </button>
        </div>
        <p className="text-center faint text-[11.5px] mt-5">Demo sign-in with pseudonymised staff and synthetic students. In production this is APU single sign-on; the same permissions are enforced by the API.</p>
      </div>
    </div>
  );
}
