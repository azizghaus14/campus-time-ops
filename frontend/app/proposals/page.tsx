"use client";
import Link from "next/link";

import { Badge, Card, Empty, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { fmtDateTime } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

const STATUS_TONE: Record<string, string> = { DRAFT: "amber", APPROVED: "accent", EXECUTED: "green", REJECTED: "red", SUPERSEDED: "neutral", INVALID: "red" };

export default function Proposals() {
  const session = useSession();
  const { data: all, error, loading } = useApi<any>(session && session.role !== "lecturer" ? "/proposals" : null, undefined, 10000);
  const { data: me } = useApi<any>(session?.role === "lecturer" ? "/me" : null);
  const data = session?.role === "lecturer" ? (me ? { proposals: me.proposals } : null) : all;
  if ((loading && !data) || !session) return <Spinner />;
  return (
    <div>
      <PageHeader title={session.role === "lecturer" ? "My requests" : "Approvals"} subtitle={session.role === "lecturer" ? "Plans drafted for your classes. You approve plans for your own sessions; campus-wide changes go to the timetabling office." : "Every plan an agent or the dashboard drafted. Only APPROVED proposals can be executed."} />
      <ErrorBox error={error} />
      <Card>
        {!data?.proposals?.length ? <Empty>No proposals yet.</Empty> : (
          <table className="data">
            <thead><tr><th>ID</th><th>Kind</th><th>Title</th><th>Status</th><th>Result</th><th>Solve</th><th>Created</th><th>Approved by</th></tr></thead>
            <tbody>
              {data.proposals.map((p: any) => (
                <tr key={p.id}>
                  <td><Link className="text-[var(--accent)] font-medium" href={`/proposals/${p.id}`}>{p.id}</Link> <span className="muted">v{p.version}</span></td>
                  <td><Badge>{p.kind}</Badge></td>
                  <td className="max-w-[340px]">{p.title}</td>
                  <td><Badge tone={STATUS_TONE[p.status]}>{p.status}</Badge></td>
                  <td className="text-xs muted">{p.kind === "REPLAN" && p.summary ? `${p.summary.substituted ?? 0} sub · ${p.summary.rescheduled ?? 0} resched · ${p.summary.placed_online} online · ${p.summary.unresolved} unresolved` : p.summary?.label}</td>
                  <td className="text-xs tabular-nums">{p.stats?.total_s != null ? `${p.stats.total_s}s` : "–"}</td>
                  <td className="text-xs muted">{fmtDateTime(p.created_at)} · {p.created_by}</td>
                  <td className="text-xs">{p.approved_by || "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
