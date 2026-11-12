"use client";
// Small visual primitives used across the app: ring gauge, segmented bar, sparkline, stat chip.
import { cn } from "@/lib/format";

export function Ring({ value, max = 100, size = 120, stroke = 10, color = "url(#ringGrad)", marker, label, sub, className }: {
  value: number; max?: number; size?: number; stroke?: number; color?: string; marker?: number; label?: React.ReactNode; sub?: React.ReactNode; className?: string;
}) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r;
  const frac = Math.max(0, Math.min(1, value / max));
  const mAng = marker != null ? (marker / max) * 2 * Math.PI - Math.PI / 2 : null;
  return (
    <div className={cn("relative inline-grid place-items-center", className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <defs>
          <linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor="#b39dff" /><stop offset="100%" stopColor="#4f8dff" /></linearGradient>
          <linearGradient id="ringRed" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor="#ff8a9a" /><stop offset="100%" stopColor="#ff5c6c" /></linearGradient>
          <linearGradient id="ringAmber" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor="#ffd36b" /><stop offset="100%" stopColor="#ff9f0a" /></linearGradient>
          <linearGradient id="ringGreen" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor="#6ee7b7" /><stop offset="100%" stopColor="#10b981" /></linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,0.07)" strokeWidth={stroke} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={stroke} fill="none" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - frac)} style={{ transition: "stroke-dashoffset 1s cubic-bezier(.2,.8,.2,1)", filter: "drop-shadow(0 0 6px rgba(139,124,255,0.5))" }} />
      </svg>
      {mAng != null && (
        <span className="absolute h-[3px] rounded-full bg-white/80" style={{
          width: stroke + 6, left: size / 2 + Math.cos(mAng) * r - (stroke + 6) / 2, top: size / 2 + Math.sin(mAng) * r - 1.5, transform: `rotate(${mAng}rad)`,
        }} />
      )}
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className="text-[22px] font-semibold tabular-nums tracking-tight leading-none">{label}</div>
          {sub && <div className="faint text-[10.5px] mt-1">{sub}</div>}
        </div>
      </div>
    </div>
  );
}

export function SegBar({ parts, height = 8, className }: { parts: { value: number; color: string; label?: string }[]; height?: number; className?: string }) {
  const total = parts.reduce((a, p) => a + p.value, 0) || 1;
  return (
    <div className={cn("flex w-full overflow-hidden rounded-full bg-white/[0.06]", className)} style={{ height }}>
      {parts.filter((p) => p.value > 0).map((p, i) => (
        <div key={i} title={`${p.label}: ${p.value}`} style={{ width: `${(p.value / total) * 100}%`, background: p.color, transition: "width .8s cubic-bezier(.2,.8,.2,1)" }}
          className="h-full first:rounded-l-full last:rounded-r-full" />
      ))}
    </div>
  );
}

export function Spark({ data, w = 90, h = 26, threshold = 80, className }: { data: number[]; w?: number; h?: number; threshold?: number; className?: string }) {
  if (!data?.length) return null;
  const lo = Math.min(threshold - 10, ...data), hi = 100;
  const pt = (v: number, i: number) => `${(i / Math.max(1, data.length - 1)) * w},${h - ((v - lo) / (hi - lo)) * h}`;
  const pts = data.map(pt).join(" ");
  const yT = h - ((threshold - lo) / (hi - lo)) * h;
  const last = data[data.length - 1];
  return (
    <svg width={w} height={h} className={cn("overflow-visible", className)}>
      <defs><linearGradient id="sparkFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#8b7cff" stopOpacity="0.35" /><stop offset="100%" stopColor="#8b7cff" stopOpacity="0" /></linearGradient></defs>
      <polygon points={`0,${h} ${pts} ${w},${h}`} fill="url(#sparkFill)" />
      <line x1={0} x2={w} y1={yT} y2={yT} stroke="var(--red)" strokeOpacity={0.6} strokeDasharray="2 3" />
      <polyline points={pts} fill="none" stroke={last < threshold ? "var(--red)" : "#a99bff"} strokeWidth={1.6} strokeLinejoin="round" />
    </svg>
  );
}

export const TYPE_META: Record<string, { color: string; soft: string; label: string }> = {
  SUBSTITUTE: { color: "var(--violet)", soft: "var(--violet-soft)", label: "Substitute" },
  RESCHEDULE: { color: "var(--green)", soft: "var(--green-soft)", label: "Rescheduled" },
  ONLINE: { color: "var(--amber)", soft: "var(--amber-soft)", label: "Online" },
  UNRESOLVED: { color: "var(--red)", soft: "var(--red-soft)", label: "Needs decision" },
};
