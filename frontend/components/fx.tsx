"use client";
// Visual effects: a living aurora rising from underneath + stardust drifting up through it.
import { useEffect, useRef } from "react";

import { cn } from "@/lib/format";

export function Aurora({ className, intensity = 1 }: { className?: string; intensity?: number }) {
  return (
    <div className={cn("aurora", className)} style={{ opacity: intensity }} aria-hidden>
      <div className="swirl" />
      <div className="blob b2" />
      <div className="blob b5" />
      <div className="blob b3" />
      <div className="blob b1" />
      <div className="blob b4" />
    </div>
  );
}

/** Pre-rendered glow sprite: tiny bright core + gaussian-like halo that fades to exactly zero (no hard rim). */
function makeSprite(rgb: [number, number, number], px = 64) {
  const c = document.createElement("canvas");
  c.width = c.height = px;
  const g = c.getContext("2d")!;
  const r = px / 2;
  const grad = g.createRadialGradient(r, r, 0, r, r, r);
  const [R, G, B] = rgb;
  const stops: [number, number][] = [[0, 1], [0.08, 1], [0.16, 0.7], [0.28, 0.3], [0.45, 0.1], [0.7, 0.03], [1, 0]];
  for (const [o, a] of stops) grad.addColorStop(o, `rgba(${R},${G},${B},${a})`);
  g.fillStyle = grad;
  g.fillRect(0, 0, px, px);
  // white-hot centre
  const core = g.createRadialGradient(r, r, 0, r, r, px * 0.06);
  core.addColorStop(0, "rgba(255,255,255,1)");
  core.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = core;
  g.fillRect(0, 0, px, px);
  return c;
}

const PALETTE: [number, number, number][] = [[214, 204, 255], [176, 160, 255], [150, 190, 255], [255, 184, 236], [240, 240, 255]];

type P = { x: number; y: number; vy: number; vx: number; size: number; life: number; max: number; spr: number; tw: number; tws: number; drift: number };

/** Canvas stardust: small crisp specks born in the glow, rising with a gentle sway, twinkling, fading smoothly. */
export function Stardust({ className, density = 1 }: { className?: string; density?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const sprites = PALETTE.map((p) => makeSprite(p));
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    let w = 0, h = 0, raf = 0, last = performance.now();
    const parts: P[] = [];
    const resize = () => {
      const r = c.getBoundingClientRect();
      w = Math.max(1, r.width); h = Math.max(1, r.height);
      c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(c);
    const target = Math.round(210 * density * Math.min(1.8, Math.max(0.5, w / 1100)));
    const spawn = (initial = false): P => {
      const spread = (Math.random() + Math.random() + Math.random() - 1.5) / 1.5; // bell-shaped, centred
      const big = Math.random() < 0.08;
      return {
        x: w / 2 + spread * w * 0.48, y: initial ? h * (0.15 + Math.random() * 0.85) : h + 4,
        vy: -(10 + Math.random() * 34), vx: (Math.random() - 0.5) * 6,
        size: big ? 12 + Math.random() * 10 : 4.5 + Math.random() * 5.5, // sprite px (core is ~6% of that)
        life: initial ? Math.random() * 8 : 0, max: 6 + Math.random() * 9,
        spr: Math.floor(Math.random() * sprites.length), tw: Math.random() * Math.PI * 2, tws: 1.5 + Math.random() * 3.5,
        drift: Math.random() * Math.PI * 2,
      };
    };
    for (let i = 0; i < target; i++) parts.push(spawn(true));
    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      ctx.clearRect(0, 0, w, h);
      ctx.globalCompositeOperation = "lighter";
      for (let i = 0; i < parts.length; i++) {
        const p = parts[i];
        p.life += dt;
        p.y += p.vy * dt;
        p.x += (p.vx + Math.sin(p.life * 0.9 + p.drift) * 5) * dt;
        const k = p.life / p.max;
        if (k >= 1 || p.y < -20) { parts[i] = spawn(); continue; }
        const fade = Math.sin(Math.PI * Math.min(1, k)) ** 1.2; // smooth in & out
        const tw = 0.7 + 0.3 * Math.sin(p.life * p.tws + p.tw);
        const heightFade = 0.45 + 0.55 * Math.min(1, p.y / h + 0.3);
        ctx.globalAlpha = Math.max(0, Math.min(1, fade * tw * heightFade));
        const s = p.size;
        ctx.drawImage(sprites[p.spr], p.x - s / 2, p.y - s / 2, s, s);
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
      if (!reduce) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, [density]);
  return <canvas ref={ref} className={cn("absolute inset-0 h-full w-full pointer-events-none", className)} aria-hidden />;
}

/** The glow pool that sits under the glass composer. */
export function ComposerGlow({ soft = false }: { soft?: boolean }) {
  return <div className={cn("composer-glow", soft && "soft")} aria-hidden><i /><i /><i /><i /></div>;
}
