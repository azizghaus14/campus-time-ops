"use client";
// The assistant's living mascot: a dotted "thinking orb" (thinking-orbs, MIT © Jakub Antalik) whose animation
// tells you what the agent is doing - breathing when idle, listening while you type, searching the timetable,
// solving the schedule, connecting/approving, composing the answer.
import { ThinkingOrb } from "thinking-orbs";
import type { OrbState } from "thinking-orbs";

import { cn } from "@/lib/format";

export type { OrbState };

const TINT = { violet: "#ddd3ff", blue: "#b8d2ff", green: "#7ef0c0", red: "#ff9aa6", white: "#f2f0ff" } as const;

export function Orb({ state = "breathing", size = 32, tint = "violet", halo = false, speed = 1, className }: {
  state?: OrbState; size?: number; tint?: keyof typeof TINT; halo?: boolean; speed?: number; className?: string;
}) {
  // the package ships tuned designs at 20 / 32 / 64 px; larger sizes scale the 64 design
  const base = size <= 24 ? 20 : size <= 44 ? 32 : 64;
  const scale = size / base;
  return (
    <span className={cn("relative inline-grid place-items-center shrink-0", className)} style={{ width: size, height: size }}>
      {halo && <span className="orb-halo" style={{ inset: -size * 0.35 }} />}
      <span style={{ width: base, height: base, transform: scale !== 1 ? `scale(${scale})` : undefined }} className="relative grid place-items-center">
        <ThinkingOrb state={state} size={base as 20 | 32 | 64} theme="dark" color={TINT[tint]} speed={speed} aria-label={`Assistant: ${state}`} />
      </span>
    </span>
  );
}

/** Guess what the agent is doing from the request, so the orb's animation matches the work. */
export function stateFor(text: string): OrbState {
  const t = text.toLowerCase();
  if (/^(yes|ok|approve|go ahead|confirm|do it)/.test(t)) return "connecting";
  if (/holiday|sick|unavailable|flood|closed|afternoon|morning|substitute/.test(t)) return "solving";
  if (/slot|viva|book|schedule|meeting|talk/.test(t)) return "weaving";
  if (/free|empty|room|lab/.test(t)) return "searching";
  if (/miss|attendance/.test(t)) return "shaping";
  return "searching";
}
