// All dashboard calls go through the Next.js proxy (/api/backend/*) which adds the bearer token server-side.
export const API = "/api/backend";

export class ApiError extends Error {
  code: string;
  details: unknown;
  status: number;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function handle<T>(r: Response): Promise<T> {
  const text = await r.text();
  let body: any = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = { error: { code: "BAD_RESPONSE", message: text.slice(0, 200) } };
  }
  if (!r.ok) {
    const e = body?.error || {};
    throw new ApiError(r.status, e.code || "HTTP_" + r.status, e.message || r.statusText, e.details);
  }
  return body as T;
}

export async function get<T = any>(path: string, params?: Record<string, string | number | boolean | undefined | null>): Promise<T> {
  const qs = params
    ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => [k, String(v)])).toString()
    : "";
  return handle<T>(await fetch(`${API}${path}${qs}`, { cache: "no-store" }));
}

export async function post<T = any>(path: string, body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(`${API}${path}`, { method: "POST", headers: { "content-type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) }),
  );
}
