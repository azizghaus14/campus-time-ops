"use client";
// Small shadcn/ui-style primitives (Tailwind + CSS variables), kept local to avoid a CLI step.
import { AlertTriangle, Loader2 } from "lucide-react";
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
    <div className={cn("flex items-start justify-between gap-3 px-4 pt-4 pb-2", className)}>
      <div className="min-w-0">
        <h3 className="text-[15px] font-semibold leading-tight">{title}</h3>
        {subtitle && <p className="muted text-xs mt-1">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

const tones: Record<string, string> = {
  neutral: "bg-[var(--panel-2)] text-[var(--muted)] border-[var(--border)]",
  accent: "bg-[var(--accent-soft)] text-[var(--accent)] border-transparent",
  red: "bg-[var(--red-soft)] text-[var(--red)] border-transparent",
  green: "bg-[var(--green-soft)] text-[var(--green)] border-transparent",
  amber: "bg-[var(--amber-soft)] text-[var(--amber)] border-transparent",
  violet: "bg-[var(--violet-soft)] text-[var(--violet)] border-transparent",
};

export function Badge({ tone = "neutral", children, className, title }: { tone?: keyof typeof tones | string; children: React.ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={cn("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-semibold whitespace-nowrap", tones[tone] || tones.neutral, className)}>
      {children}
    </span>
  );
}

export function Button({
  variant = "default", size = "md", loading, className, children, ...p
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "outline" | "ghost" | "danger" | "success"; size?: "sm" | "md"; loading?: boolean }) {
  const v = {
    default: "bg-[var(--accent)] text-white hover:opacity-90",
    outline: "border border-[var(--border)] bg-[var(--panel)] hover:bg-[var(--panel-2)]",
    ghost: "hover:bg-[var(--panel-2)]",
    danger: "bg-[var(--red)] text-white hover:opacity-90",
    success: "bg-[var(--green)] text-white hover:opacity-90",
  }[variant];
  const s = size === "sm" ? "h-7 px-2.5 text-xs" : "h-9 px-3.5 text-sm";
  return (
    <button className={cn("inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition disabled:opacity-50 disabled:cursor-not-allowed", v, s, className)} disabled={loading || p.disabled} {...p}>
      {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      {children}
    </button>
  );
}

export function Input({ className, ...p }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn("h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--panel)] px-3 text-sm outline-none focus:border-[var(--accent)]", className)} {...p} />;
}

export function Select({ className, children, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn("h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--panel)] px-2.5 text-sm outline-none focus:border-[var(--accent)]", className)} {...p}>
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
    <Card className="px-4 py-3.5">
      <div className="muted text-xs font-medium">{label}</div>
      <div className={cn("mt-1 text-[26px] font-semibold tabular-nums leading-none", color)}>{value}</div>
      {sub && <div className="muted mt-1.5 text-[11px] leading-snug">{sub}</div>}
    </Card>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 muted text-sm p-6">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error as { message?: string; code?: string; details?: unknown };
  return (
    <div className="rounded-lg border border-[var(--red)]/40 bg-[var(--red-soft)] px-3 py-2 text-sm text-[var(--red)] flex gap-2">
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
        <h1 className="text-[22px] font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="muted text-sm mt-1 max-w-3xl">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}
