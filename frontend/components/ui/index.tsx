"use client";
// Small shadcn/ui-style primitives (Tailwind + CSS variables), kept local to avoid a CLI step.
import { AlertTriangle, Loader2 } from "lucide-react";

import { Orb } from "@/components/orb";
import * as React from "react";

import { cn } from "@/lib/format";

export function Card({ className, children, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("panel", className)} {...p}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, right, className }: { title: React.ReactNode; subtitle?: React.ReactNode; right?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start justify-between gap-3 px-5 pt-5 pb-3", className)}>
      <div className="min-w-0">
        <h3 className="text-[15px] font-semibold leading-tight tracking-tight">{title}</h3>
        {subtitle && <p className="muted text-xs mt-1">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

const tones: Record<string, string> = {
  neutral: "bg-white/[0.05] text-[var(--muted)] border-[var(--border)]",
  accent: "bg-[var(--accent-soft)] text-[var(--accent)] border-transparent",
  red: "bg-[var(--red-soft)] text-[var(--red)] border-transparent",
  green: "bg-[var(--green-soft)] text-[var(--green)] border-transparent",
  amber: "bg-[var(--amber-soft)] text-[var(--amber)] border-transparent",
  violet: "bg-[var(--violet-soft)] text-[var(--violet)] border-transparent",
};

export function Badge({ tone = "neutral", children, className, title }: { tone?: keyof typeof tones | string; children: React.ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold tracking-wide whitespace-nowrap", tones[tone] || tones.neutral, className)}>
      {children}
    </span>
  );
}

export function Button({
  variant = "default", size = "md", loading, className, children, ...p
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "outline" | "ghost" | "danger" | "success"; size?: "sm" | "md"; loading?: boolean }) {
  const v = {
    default: "btn-gradient text-white hover:brightness-110",
    outline: "border border-[var(--border-strong)] bg-white/[0.04] hover:bg-white/[0.08] backdrop-blur",
    ghost: "hover:bg-white/[0.06]",
    danger: "bg-[var(--red)]/90 text-white hover:bg-[var(--red)]",
    success: "bg-gradient-to-br from-emerald-400 to-teal-500 text-[#04120c] font-semibold hover:brightness-110 shadow-[0_8px_24px_-8px_rgba(52,211,153,0.6)]",
  }[variant];
  const s = size === "sm" ? "h-8 px-3 text-xs" : "h-10 px-4 text-sm";
  return (
    <button className={cn("inline-flex items-center justify-center gap-1.5 rounded-full font-medium transition active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed", v, s, className)} disabled={loading || p.disabled} {...p}>
      {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      {children}
    </button>
  );
}

export function Input({ className, ...p }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn("h-10 w-full rounded-xl border border-[var(--border)] bg-white/[0.04] px-3.5 text-sm outline-none transition focus:border-[var(--accent)] focus:bg-white/[0.06] placeholder:text-[var(--faint)]", className)} {...p} />;
}

export function Select({ className, children, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn("h-10 w-full rounded-xl border border-[var(--border)] bg-[#16161d] px-3 text-sm outline-none focus:border-[var(--accent)]", className)} {...p}>
      {children}
    </select>
  );
}

export function Label({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <label className="block text-xs font-medium muted mb-1">
      {children} {hint && <span className="font-normal opacity-70">· {hint}</span>}
    </label>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: "red" | "green" | "accent" | "amber" | "violet" }) {
  const color = tone ? `text-[var(--${tone})]` : "";
  return (
    <Card className="px-5 py-4">
      <div className="muted text-xs font-medium">{label}</div>
      <div className={cn("mt-1.5 text-[28px] font-semibold tabular-nums leading-none tracking-tight", color)}>{value}</div>
      {sub && <div className="muted mt-1.5 text-[11px] leading-snug">{sub}</div>}
    </Card>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 muted text-sm p-6">
      <Orb state="searching" size={32} tint="violet" /> {label}
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error as { message?: string; code?: string; details?: unknown };
  return (
    <div className="rounded-xl border border-[var(--red)]/30 bg-[var(--red-soft)] px-3.5 py-2.5 text-sm text-[var(--red)] flex gap-2">
      <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
      <div>
        <b>{e.code || "Error"}</b> — {e.message || String(error)}
        {e.code === "BACKEND_UNREACHABLE" && <div className="text-xs mt-1">Start it with <code>make backend</code>.</div>}
        {!!e.details && typeof e.details === "object" && "suggestions" in (e.details as any) && (
          <div className="text-xs mt-1">Did you mean: {JSON.stringify((e.details as any).suggestions)}</div>
        )}
      </div>
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="muted text-sm p-6 text-center">{children}</div>;
}

export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
      <div>
        <h1 className="text-[28px] font-semibold tracking-[-0.025em]">{title}</h1>
        {subtitle && <p className="muted text-sm mt-1 max-w-3xl">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}
