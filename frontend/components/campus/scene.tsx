"use client";
// Three.js campus: dark glass buildings with glowing edges; every room is a block lit by its live state.
import { Edges, Grid, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Bloom, EffectComposer, Vignette } from "@react-three/postprocessing";
import { useMemo, useRef, useState } from "react";
import * as THREE from "three";

import { cn } from "@/lib/format";

export type RoomState = "free" | "used" | "affected" | "moved" | "pending";
export type Mode = "live" | "heat" | "week";

const C = {
  slab: "#15151d", edge: "#6a5cff", free: "#262633", used: "#7a67ff", affected: "#ff4d5e", moved: "#2ee59d", pending: "#34d399",
};

function heatColor(u: number) {
  // 0 deep indigo -> violet -> magenta -> amber
  const stops = [[0, "#1c1f3a"], [0.25, "#3b3fae"], [0.5, "#7a5cff"], [0.75, "#d24dff"], [1, "#ffb24d"]] as const;
  for (let i = 1; i < stops.length; i++) {
    if (u <= stops[i][0]) {
      const [a, ca] = stops[i - 1], [b, cb] = stops[i];
      return new THREE.Color(ca).lerp(new THREE.Color(cb), (u - a) / (b - a));
    }
  }
  return new THREE.Color(stops[stops.length - 1][1]);
}

function useMaterials() {
  return useMemo(() => ({
    slab: new THREE.MeshStandardMaterial({ color: C.slab, transparent: true, opacity: 0.55, roughness: 0.25, metalness: 0.6 }),
    free: new THREE.MeshStandardMaterial({ color: C.free, transparent: true, opacity: 0.55, roughness: 0.6 }),
    used: new THREE.MeshStandardMaterial({ color: C.used, emissive: new THREE.Color("#5240ff"), emissiveIntensity: 1.1, roughness: 0.35 }),
    affected: new THREE.MeshStandardMaterial({ color: C.affected, emissive: new THREE.Color("#ff2a40"), emissiveIntensity: 1.4, roughness: 0.4 }),
    moved: new THREE.MeshStandardMaterial({ color: C.moved, emissive: new THREE.Color("#10c27f"), emissiveIntensity: 1.1, roughness: 0.4 }),
    pending: new THREE.MeshStandardMaterial({ color: C.pending, emissive: new THREE.Color("#10c27f"), emissiveIntensity: 0.6, transparent: true, opacity: 0.75 }),
    dim: new THREE.MeshStandardMaterial({ color: "#1a1a22", transparent: true, opacity: 0.18 }),
  }), []);
}

function Pulse({ m }: { m: THREE.MeshStandardMaterial }) {
  useFrame(({ clock }) => { m.emissiveIntensity = 0.9 + Math.sin(clock.elapsedTime * 4) * 0.7; });
  return null;
}

type Props = {
  layout: any; states: Record<string, RoomState>; util: Record<string, number>; mode: Mode;
  selected: string | null; floor: number | null; hoverRoom: string | null;
  onSelect: (id: string | null) => void; onRoom: (name: string | null) => void; onHover: (name: string | null) => void;
  pins: Record<string, { used: number; total: number; affected: number }>;
};

function Building({ b, p, mats, heatMats }: { b: any; p: Props; mats: ReturnType<typeof useMaterials>; heatMats: Record<string, THREE.Material> }) {
  const sel = p.selected === b.id;
  const dim = p.selected !== null && !sel;
  const gap = useRef(1);
  const refs = useRef<(THREE.Group | null)[]>([]);
  const FH = p.layout.floor_height;
  useFrame((_, dt) => {
    const target = sel ? 2.1 : 1;
    gap.current += (target - gap.current) * Math.min(1, dt * 5);
    refs.current.forEach((g, i) => { if (g) g.position.y = i * FH * gap.current; });
  });
  return (
    <group position={[b.x, 0, b.z]}>
      {b.floors.map((f: any, i: number) => {
        const floorDim = dim || (sel && p.floor !== null && p.floor !== f.level);
        return (
          <group key={f.level} ref={(g) => { refs.current[i] = g; }}>
            <mesh position={[0, 0.11, 0]} material={floorDim ? mats.dim : mats.slab}
              onClick={(e) => { e.stopPropagation(); p.onSelect(sel ? null : b.id); }}>
              <boxGeometry args={[b.w, 0.22, b.d]} />
              <Edges color={sel ? "#a99bff" : C.edge} threshold={15} transparent opacity={floorDim ? 0.15 : sel ? 0.9 : 0.55} />
            </mesh>
            {f.rooms.map((r: any) => {
              const st = p.states[r.name] || "free";
              const mat = floorDim ? mats.dim : p.mode !== "live" ? heatMats[r.name] : (mats as any)[st];
              const h = p.mode !== "live" ? 0.3 + Math.min(1, (p.util[r.name] || 0) * 1.6) * 1.5 : st === "free" ? 0.5 : 1.45;
              const hov = p.hoverRoom === r.name;
              return (
                <mesh key={r.name} position={[r.x, 0.22 + h / 2, r.z]} material={mat} scale={hov ? [1.08, 1.08, 1.08] : [1, 1, 1]}
                  onPointerOver={(e) => { e.stopPropagation(); p.onHover(r.name); }} onPointerOut={() => p.onHover(null)}
                  onClick={(e) => { e.stopPropagation(); if (!sel) p.onSelect(b.id); p.onRoom(r.name); }}>
                  <boxGeometry args={[p.layout.cell * 0.8, h, p.layout.cell * 0.8]} />
                </mesh>
              );
            })}
          </group>
        );
      })}
    </group>
  );
}

function Scene(p: Props) {
  const mats = useMaterials();
  const heatMats = useMemo(() => {
    const out: Record<string, THREE.Material> = {};
    for (const b of p.layout.buildings) for (const f of b.floors) for (const r of f.rooms) {
      const u = Math.min(1, (p.util[r.name] || 0) * 1.6);
      const c = heatColor(u);
      out[r.name] = new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: 0.6 + u * 1.4, roughness: 0.4 });
    }
    return out;
  }, [p.layout, p.util]);
  return (
    <>
      <color attach="background" args={["#040406"]} />
      <fog attach="fog" args={["#040406", 130, 280]} />
      <ambientLight intensity={0.35} />
      <directionalLight position={[40, 80, 30]} intensity={0.7} />
      <pointLight position={[-40, 30, -30]} color="#5b6bff" intensity={2200} distance={160} />
      <pointLight position={[50, 25, 40]} color="#a855f7" intensity={1600} distance={160} />
      <Pulse m={mats.affected} />
      <Grid args={[260, 260]} position={[0, 0, 0]} cellSize={2} cellThickness={0.5} cellColor="#16161f" sectionSize={12} sectionThickness={1}
        sectionColor="#2a2650" fadeDistance={190} fadeStrength={1.6} infiniteGrid />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.02, 0]} onClick={() => p.onSelect(null)}>
        <circleGeometry args={[95, 64]} />
        <meshStandardMaterial color="#0a0a10" transparent opacity={0.85} />
      </mesh>
      {p.layout.buildings.map((b: any) => <Building key={b.id} b={b} p={p} mats={mats} heatMats={heatMats} />)}
      <EffectComposer multisampling={4}>
        <Bloom intensity={0.9} luminanceThreshold={0.18} luminanceSmoothing={0.35} mipmapBlur radius={0.7} />
        <Vignette eskil={false} offset={0.25} darkness={0.75} />
      </EffectComposer>
      <OrbitControls makeDefault enableDamping dampingFactor={0.08} minDistance={40} maxDistance={220} maxPolarAngle={Math.PI / 2.3} target={[0, 6, 2]} />
    </>
  );
}

/** Projects each building's roof point to screen space every frame and moves the DOM pin (no React re-render). */
function PinProjector({ layout, selected, refs }: { layout: any; selected: string | null; refs: React.MutableRefObject<Record<string, HTMLDivElement | null>> }) {
  const { camera, size } = useThree();
  const v = useMemo(() => new THREE.Vector3(), []);
  useFrame(() => {
    for (const b of layout.buildings) {
      const el = refs.current[b.id];
      if (!el) continue;
      const top = b.floors.length * layout.floor_height * (selected === b.id ? 2.1 : 1) + 2.5;
      v.set(b.x, top, b.z).project(camera);
      const x = (v.x * 0.5 + 0.5) * size.width, y = (-v.y * 0.5 + 0.5) * size.height;
      el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -100%)`;
      el.style.visibility = v.z > 1 ? "hidden" : "visible";
    }
  });
  return null;
}

export default function CampusCanvas(props: Props) {
  const [ready, setReady] = useState(false);
  const pinRefs = useRef<Record<string, HTMLDivElement | null>>({});
  return (
    <div className="relative h-full w-full">
      <Canvas camera={{ position: [122, 108, 122], fov: 30, near: 1, far: 600 }} dpr={[1, 2]} gl={{ antialias: true }}
        onCreated={() => setReady(true)} style={{ opacity: ready ? 1 : 0, transition: "opacity .6s" }}>
        <Scene {...props} />
        <PinProjector layout={props.layout} selected={props.selected} refs={pinRefs} />
      </Canvas>
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        {props.layout.buildings.map((b: any) => {
          const pin = props.pins[b.id] || { used: 0, total: b.rooms, affected: 0 };
          const dim = props.selected !== null && props.selected !== b.id;
          return (
            <div key={b.id} ref={(el) => { pinRefs.current[b.id] = el; }} className="absolute left-0 top-0 will-change-transform"
              style={{ opacity: dim ? 0 : 1, transition: "opacity .3s" }}>
              <button onClick={() => props.onSelect(props.selected === b.id ? null : b.id)} className={cn("select-none whitespace-nowrap flex items-center gap-2 rounded-full border bg-[#14141c]/80 backdrop-blur-md pl-1 pr-3 py-1 shadow-[0_10px_30px_-10px_rgba(0,0,0,.8)]", dim ? "pointer-events-none" : "pointer-events-auto", pin.affected ? "border-[var(--red)]/50" : "border-white/15")}>
                <span className="relative grid place-items-center h-7 w-7 rounded-full" style={{ background: `conic-gradient(${pin.affected ? "#ff5c6c" : "#8b7cff"} ${(pin.used / Math.max(1, pin.total)) * 360}deg, rgba(255,255,255,.08) 0)` }}>
                  <span className="absolute inset-[3px] rounded-full bg-[#14141c]" />
                  <span className="relative text-[10.5px] font-semibold text-white">{pin.used}</span>
                </span>
                <span className="text-left leading-tight"><span className="block text-[11.5px] font-semibold text-white">{b.name}</span><span className="block text-[9.5px] text-white/50">{pin.used}/{pin.total} in use{pin.affected ? ` · ${pin.affected} affected` : ""}</span></span>
              </button>
              <div className="mx-auto h-3 w-px bg-gradient-to-b from-white/40 to-transparent" />
            </div>
          );
        })}
      </div>
    </div>
  );
}
