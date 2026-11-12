"use client";
import Link from "next/link";

import { Badge, Card, Empty, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/use-api";

function tone(what: string) {
  if (what.includes("approved")) return "green";
  if (what.includes("rejected")) return "red";
  if (what.includes("executed") || what.startsWith("calendar") || what.startsWith("gmail") || what.startsWith("docs") || what.startsWith("timetable")) return "violet";
  if (what.includes("drafted")) return "amber";
  return "neutral";
}

export default function Audit() {
  const { data, error, loading } = useApi<any>("/audit", { limit: 500 }, 10000);
  if (loading && !data) return <Spinner />;
  return (
    <div>
      <PageHeader title="Audit log" subtitle="Append-only record of every disruption, proposal, approval and action — who, what, when, before and after." />
      <ErrorBox error={error} />
      <Card>
        {!data?.events?.length ? <Empty>No events yet.</Empty> : (
          <table className="data">
            <thead><tr><th>ID</th><th>When (demo clock)</th><th>Who</th><th>What</th><th>Proposal</th><th>Details</th></tr></thead>
            <tbody>
              {data.events.map((e: any) => (
                <tr key={e.id}>
                  <td className="mono text-xs">{e.id}</td>
                  <td className="text-xs whitespace-nowrap">{fmtDateTime(e.when)}<div className="muted text-[10px]">wall {fmtDateTime(e.wall_clock)}</div></td>
                  <td className="text-xs">{e.who}</td>
                  <td><Badge tone={tone(e.what)}>{e.what}</Badge></td>
                  <td>{e.proposal_id ? <Link className="text-[var(--accent)] text-xs" href={`/proposals/${e.proposal_id}`}>{e.proposal_id}</Link> : "–"}</td>
                  <td className="text-[11px] muted max-w-[520px]">
                    <details><summary className="cursor-pointer truncate">{JSON.stringify(e.after ?? e.before ?? {}).slice(0, 110)}</summary>
                      <pre className="whitespace-pre-wrap text-[10px] mt-1 max-h-56 overflow-auto">{JSON.stringify({ before: e.before, after: e.after }, null, 1)}</pre>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
