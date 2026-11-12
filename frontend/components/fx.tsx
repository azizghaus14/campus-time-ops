"use client";
// Visual effects: aurora light rising from underneath + stardust particles drifting up through it.
import { useEffect, useRef } from "react";

import { cn } from "@/lib/format";

export function Aurora({ className, intensity = 1 }: { className?: string; intensity?: number }) {
  return (
    <div className={cn("aurora", className)} style={{ opacity: intensity }} aria-hidden>
      <div className="blob b2" />
      <div className="blob b3" />
      <div className="blob b1" />
      <div className="blob b4" />
    </div>
  );
}

type P = { x: number; y: number; vy: number; vx: number; r: number; life: number; max: number; hue: number; tw: number };

/** Canvas stardust: particles spawn near the bottom (inside the glow), rise with a gentle sway, twinkle and fade. */
export function Stardust({ className, density = 1 }: { className?: string; density?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0, h = 0, raf = 0;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const parts: P[] = [];
    const resize = () => {
      const r = c.getBoundingClientRect();
      w = r.width; h = r.height;
      c.width = w * dpr; c.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(c);
    const target = Math.round(90 * density * Math.min(1.6, w / 900 + 0.4));
    const spawn = (initial = false): P => {
      // concentrated around the centre, like light leaking up from below
      const cx = w / 2 + (Math.random() + Math.random() + Math.random() - 1.5) * w * 0.38;
      const max = 260 + Math.random() * 420;
      return {
        x: cx, y: initial ? h * (0.35 + Math.random() * 0.65) : h + 6, vy: -(0.18 + Math.random() * 0.55), vx: (Math.random() - 0.5) * 0.12,
        r: Math.random() < 0.85 ? 0.5 + Math.random() * 0.9 : 1.4 + Math.random() * 1.1, life: initial ? Math.random() * max : 0, max,
        hue: [255, 228, 205, 290][Math.floor(Math.random() * 4)], tw: Math.random() * Math.PI * 2,
      };
    };
    for (let i = 0; i < target; i++) parts.push(spawn(true));
    let t = 0;
    const tick = () => {
      t += 1;
      ctx.clearRect(0, 0, w, h);
      for (let i = 0; i < parts.length; i++) {
        const p = parts[i];
        p.life += 1;
        p.y += p.vy;
        p.x += p.vx + Math.sin((p.life + p.tw * 50) / 60) * 0.12;
        const k = p.life / p.max;
        const fade = k < 0.15 ? k / 0.15 : k > 0.7 ? Math.max(0, (1 - k) / 0.3) : 1;
        const tw = 0.65 + 0.35 * Math.sin(t / 14 + p.tw);
        const a = fade * tw * (0.25 + 0.75 * (p.y / h));
        if (p.life >= p.max || p.y < -10) { parts[i] = spawn(); continue; }
        const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 4);
        g.addColorStop(0, `hsla(${p.hue}, 100%, 88%, ${a})`);
        g.addColorStop(0.35, `hsla(${p.hue}, 100%, 75%, ${a * 0.45})`);
        g.addColorStop(1, `hsla(${p.hue}, 100%, 70%, 0)`);
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r * 4, 0, Math.PI * 2);
        ctx.fill();
      }
      if (!reduce) raf = requestAnimationFrame(tick);
    };
    tick();
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, [density]);
  return <canvas ref={ref} className={cn("absolute inset-0 h-full w-full pointer-events-none", className)} aria-hidden />;
}

/** A glass panel with the aurora + stardust glowing up from underneath (used to highlight key moments). */
export function GlowStage({ children, className, height = "auto" }: { children: React.ReactNode; className?: string; height?: string }) {
  return (
    <div className={cn("relative overflow-hidden rounded-[28px]", className)} style={{ height }}>
      <Aurora intensity={0.7} />
      <Stardust density={0.6} />
      <div className="relative">{children}</div>
    </div>
  );
}
