// Server-side proxy to the FastAPI backend. The browser never sees the bearer token.
// The demo persona (cookies) is forwarded as X-Demo-Role / X-Demo-User so the backend can enforce role permissions.
import { NextRequest } from "next/server";

const BACKEND = process.env.BACKEND_URL || "http://localhost:8000";
const TOKEN = process.env.MCP_AUTH_TOKEN || "";

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const url = `${BACKEND}/api/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const headers: Record<string, string> = { "content-type": req.headers.get("content-type") || "application/json" };
  if (TOKEN) headers.authorization = `Bearer ${TOKEN}`;
  const role = req.cookies.get("cto_role")?.value;
  const user = req.cookies.get("cto_user")?.value;
  if (role) headers["x-demo-role"] = role;
  if (user) headers["x-demo-user"] = decodeURIComponent(user);
  try {
    const r = await fetch(url, {
      method: req.method,
      headers,
      body: req.method === "GET" || req.method === "HEAD" ? undefined : await req.text(),
      cache: "no-store",
    });
    return new Response(await r.text(), { status: r.status, headers: { "content-type": r.headers.get("content-type") || "application/json" } });
  } catch {
    return Response.json({ error: { code: "BACKEND_UNREACHABLE", message: `Backend not reachable at ${BACKEND}` } }, { status: 502 });
  }
}

export const GET = forward;
export const POST = forward;
export const dynamic = "force-dynamic";
