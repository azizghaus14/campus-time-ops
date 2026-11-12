"use client";
// Demo sign-in: the persona lives in cookies so the Next.js proxy can forward it to the backend as
// X-Demo-Role / X-Demo-User. Production would use APU SSO; the backend permission checks stay the same.
import { useEffect, useState } from "react";

export type Role = "admin" | "lecturer" | "student";
export type Session = { role: Role; user: string; name: string };

function read(name: string) {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : "";
}

export function getSession(): Session | null {
  if (typeof document === "undefined") return null;
  const role = read("cto_role") as Role;
  if (!["admin", "lecturer", "student"].includes(role)) return null;
  return { role, user: read("cto_user"), name: read("cto_name") };
}

export function setSession(s: Session) {
  const opt = "; path=/; max-age=604800; SameSite=Lax";
  document.cookie = `cto_role=${encodeURIComponent(s.role)}${opt}`;
  document.cookie = `cto_user=${encodeURIComponent(s.user)}${opt}`;
  document.cookie = `cto_name=${encodeURIComponent(s.name)}${opt}`;
}

export function clearSession() {
  for (const k of ["cto_role", "cto_user", "cto_name"]) document.cookie = `${k}=; path=/; max-age=0`;
}

export function useSession() {
  const [s, setS] = useState<Session | null | undefined>(undefined);
  useEffect(() => setS(getSession()), []);
  return s; // undefined = not yet read (SSR/first paint), null = signed out
}
