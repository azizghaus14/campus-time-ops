// Everything is shown in MYT (Asia/Kuala_Lumpur, UTC+8) regardless of the viewer's machine.
const TZ = "Asia/Kuala_Lumpur";

export function fmtDate(iso: string, opts: Intl.DateTimeFormatOptions = { weekday: "short", day: "2-digit", month: "short" }) {
  const d = iso.length <= 10 ? new Date(iso + "T12:00:00+08:00") : new Date(iso);
  return new Intl.DateTimeFormat("en-GB", { timeZone: TZ, ...opts }).format(d);
}

export function fmtTime(iso: string) {
  return new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(iso));
}

export function fmtDateTime(iso: string) {
  return `${fmtDate(iso)} ${fmtTime(iso)}`;
}

export function pct(x: number | null | undefined, digits = 0) {
  return x === null || x === undefined ? "–" : `${(x * 100).toFixed(digits)}%`;
}

export function num(x: number | null | undefined) {
  return x === null || x === undefined ? "–" : new Intl.NumberFormat("en-GB").format(x);
}

export function cn(...xs: (string | false | null | undefined)[]) {
  return xs.filter(Boolean).join(" ");
}
