"use client";
import {
  Activity, CalendarClock, CalendarSearch, ClipboardList, DoorOpen, GaugeCircle, LayoutDashboard, Moon, ShieldCheck, Sun, UserRoundCheck, Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/disruptions", label: "Disruptions", icon: Zap },
  { href: "/proposals", label: "Proposals", icon: ClipboardList },
  { href: "/slots", label: "Slot Finder", icon: CalendarSearch },
  { href: "/rooms", label: "Rooms", icon: DoorOpen },
  { href: "/health", label: "Timetable Health", icon: Activity },
  { href: "/attendance", label: "Attendance Risk", icon: UserRoundCheck },
  { href: "/audit", label: "Audit log", icon: ShieldCheck },
];

function ThemeToggle() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    let saved: string | null = null;
    try { saved = localStorage.getItem("cto-theme"); } catch {}
    const d = saved ? saved === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    setDark(d);
    document.documentElement.classList.toggle("dark", d);
  }, []);
  return (
    <button
      aria-label="Toggle dark mode"
      className="h-8 w-8 grid place-items-center rounded-lg hover:bg-[var(--panel-2)]"
      onClick={() => {
        const d = !dark;
        setDark(d);
        document.documentElement.classList.toggle("dark", d);
        try { localStorage.setItem("cto-theme", d ? "dark" : "light"); } catch {}
      }}
    >
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { data: health, error } = useApi<any>("/health", undefined, 30000);
  return (
    <div className="min-h-screen flex">
      <aside className="hidden md:flex w-56 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--panel)] sticky top-0 h-screen">
        <div className="px-4 py-4 flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-[var(--accent)] grid place-items-center text-white"><CalendarClock className="h-4 w-4" /></div>
          <div>
            <div className="font-semibold text-sm leading-tight">Campus Time Ops</div>
            <div className="muted text-[11px]">APU timetable agents</div>
          </div>
        </div>
        <nav className="px-2 flex-1 space-y-0.5">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <Link key={href} href={href}
                className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm ${active ? "bg-[var(--accent-soft)] text-[var(--accent)] font-medium" : "hover:bg-[var(--panel-2)]"}`}>
                <Icon className="h-4 w-4" /> {label}
              </Link>
            );
          })}
        </nav>
        <div className="p-3 text-[11px] muted border-t border-[var(--border)] space-y-1">
          <div className="flex items-center gap-1.5"><GaugeCircle className="h-3.5 w-3.5" /> Human approves every action</div>
          <div>Public APU feed · pseudonymised · synthetic students</div>
        </div>
      </aside>
      <div className="flex-1 min-w-0">
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-[var(--border)] bg-[var(--panel)]/90 backdrop-blur px-4 md:px-6 h-12">
          <div className="flex md:hidden gap-1 overflow-x-auto text-xs">
            {NAV.map((n) => <Link key={n.href} href={n.href} className="px-2 py-1 rounded whitespace-nowrap hover:bg-[var(--panel-2)]">{n.label}</Link>)}
          </div>
          <div className="hidden md:block text-xs muted">
            {error ? <span className="text-[var(--red)]">Backend offline — run <code>make backend</code></span> : health ? (
              <>Clock <b className="text-[var(--text)]">{fmtDateTime(health.now)} MYT</b> · data <b className="text-[var(--text)]">{health.data_mode}</b> · {health.sessions.toLocaleString()} physical sessions · Workspace <b className="text-[var(--text)]">{health.workspace}</b></>
            ) : "Connecting…"}
          </div>
          <ThemeToggle />
        </header>
        <main className="px-4 md:px-6 py-6 max-w-[1500px]">{children}</main>
      </div>
    </div>
  );
}
