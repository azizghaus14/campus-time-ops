"use client";
import {
  Activity, Box, CalendarDays, CalendarSearch, ClipboardCheck, DoorOpen, LogOut, ShieldCheck, Sparkles, UserRoundCheck, Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Orb } from "@/components/orb";
import { cn, fmtDateTime } from "@/lib/format";
import { clearSession, Role, useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

type Item = { href: string; label: string; icon: any };
export const NAV: Record<Role, Item[]> = {
  admin: [
    { href: "/", label: "Assistant", icon: Sparkles },
    { href: "/campus", label: "Campus", icon: Box },
    { href: "/disruptions", label: "Live board", icon: Zap },
    { href: "/proposals", label: "Approvals", icon: ClipboardCheck },
    { href: "/slots", label: "Slot Finder", icon: CalendarSearch },
    { href: "/rooms", label: "Rooms", icon: DoorOpen },
    { href: "/health", label: "Health", icon: Activity },
    { href: "/attendance", label: "Attendance", icon: UserRoundCheck },
    { href: "/audit", label: "Audit log", icon: ShieldCheck },
  ],
  lecturer: [
    { href: "/", label: "Assistant", icon: Sparkles },
    { href: "/week", label: "My week", icon: CalendarDays },
    { href: "/proposals", label: "My requests", icon: ClipboardCheck },
    { href: "/slots", label: "Slot Finder", icon: CalendarSearch },
    { href: "/campus", label: "Campus", icon: Box },
  ],
  student: [
    { href: "/", label: "Assistant", icon: Sparkles },
    { href: "/week", label: "My timetable", icon: CalendarDays },
    { href: "/attendance", label: "Attendance", icon: UserRoundCheck },
    { href: "/campus", label: "Free rooms", icon: Box },
  ],
};
const ROLE_LABEL: Record<Role, string> = { admin: "Timetabling Office", lecturer: "Lecturer", student: "Student" };

function allowed(role: Role, path: string) {
  if (path === "/") return true;
  if (role === "admin") return true;
  return NAV[role].some((n) => n.href !== "/" && path.startsWith(n.href)) || (role === "lecturer" && path.startsWith("/proposals/"));
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const session = useSession();
  const { data: health } = useApi<any>(session ? "/health" : null, undefined, 30000);
  const bare = path === "/login";

  useEffect(() => {
    if (session === null && !bare) router.replace("/login");
    else if (session && !bare && !allowed(session.role, path)) router.replace("/");
  }, [session, bare, path, router]);

  if (bare) return <>{children}</>;
  if (!session) return <div className="min-h-screen" />;

  const nav = NAV[session.role];
  const initials = session.name.replace(/^(Dr\.|Ms\.|Mr\.|Prof\.|Assoc\. Prof\.|Ts\.)\s*/, "").split(" ").map((x) => x[0]).join("").slice(0, 2);
  return (
    <div className="min-h-screen">
      <aside className="hidden md:flex fixed left-3 top-3 bottom-3 w-[236px] z-40 flex-col">
        <div className="glass-strong flex-1 flex flex-col !rounded-[26px] overflow-hidden">
          <div className="px-4 pt-5 pb-4 flex items-center gap-2.5">
            <Orb state="weaving" size={36} tint="violet" />
            <div className="leading-tight">
              <div className="font-semibold text-[14px] tracking-tight">Campus Time Ops</div>
              <div className="faint text-[11px]">APU · live timetable</div>
            </div>
          </div>
          <nav className="px-2 flex-1 space-y-0.5">
            {nav.map(({ href, label, icon: Icon }) => {
              const active = href === "/" ? path === "/" : path.startsWith(href);
              return (
                <Link key={href} href={href}
                  className={cn("group flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13.5px] transition",
                    active ? "bg-white/[0.08] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]" : "text-[var(--muted)] hover:text-white hover:bg-white/[0.04]")}>
                  <Icon className={cn("h-[17px] w-[17px]", active ? "text-[var(--accent)]" : "")} />
                  {label}
                </Link>
              );
            })}
          </nav>
          <div className="m-2 rounded-2xl bg-white/[0.04] border border-[var(--border)] p-3">
            <div className="flex items-center gap-2.5">
              <div className="h-8 w-8 rounded-full bg-gradient-to-br from-violet-400/80 to-blue-500/80 grid place-items-center text-[11px] font-semibold">{initials}</div>
              <div className="min-w-0 leading-tight">
                <div className="text-[12.5px] font-medium truncate">{session.name}</div>
                <div className="faint text-[11px]">{ROLE_LABEL[session.role]}{session.role !== "admin" ? ` · ${session.user}` : ""}</div>
              </div>
            </div>
            <button onClick={() => { clearSession(); window.location.href = "/login"; }}
              className="mt-2.5 w-full flex items-center justify-center gap-1.5 rounded-lg py-1.5 text-[11.5px] muted hover:text-white hover:bg-white/[0.05]">
              <LogOut className="h-3.5 w-3.5" /> Switch persona
            </button>
          </div>
        </div>
      </aside>
      <div className="min-w-0 md:pl-[260px]">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 px-4 md:px-8 h-14 bg-gradient-to-b from-[var(--bg)]/90 via-[var(--bg)]/55 to-transparent">
          <div className="flex md:hidden gap-1 overflow-x-auto text-xs">
            {nav.map((n) => <Link key={n.href} href={n.href} className="px-2.5 py-1 rounded-full whitespace-nowrap bg-white/[0.04]">{n.label}</Link>)}
          </div>
          <div className="hidden md:flex items-center gap-2 text-[12px] muted">
            <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full rounded-full bg-[var(--green)] opacity-60 animate-ping" /><span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--green)]" /></span>
            {health ? <>Live · <span className="text-white/90">{fmtDateTime(health.now)} MYT</span> · {health.sessions.toLocaleString()} sessions · {health.data_mode}</> : "Connecting…"}
          </div>
          <div className="text-[11px] faint hidden md:block">Every change needs a human approval</div>
        </header>
        <main className="relative px-4 md:px-8 py-7 max-w-[1520px]">{children}</main>
      </div>
    </div>
  );
}
