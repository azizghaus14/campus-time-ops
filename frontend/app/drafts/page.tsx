"use client";
// Every approved (executed) plan and its email drafts, so drafts are always reachable from the sidebar.
import Link from "next/link";
import { Mail } from "lucide-react";

import { Badge, Card, Empty, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { fmtDateTime } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

export default function DraftsIndex() {
  const session = useSession();
  const { data: all, error, loading } = useApi<any>(session && session.role !== "lecturer" ? "/proposals" : null, { status: "EXECUTED" }, 10000);
  const { data: me } = useApi<any>(session?.role === "lecturer" ? "/me" : null);
  const list: any[] = session?.role === "lecturer" ? (me?.proposals || []).filter((p: any) => p.status === "EXECUTED") : all?.proposals || [];
  if ((loading && !all && !me) || !session) return <Spinner />;
  return (
    <div>
      <PageHeader title="Email drafts"
        subtitle="Every approved plan writes its emails as drafts. Nothing is sent automatically: open a plan, review each email and press Send." />
      <ErrorBox error={error} />
      <Card className="p-2">
        {!list.length ? <Empty>No approved plans yet. Approve a plan and its email drafts appear here.</Empty> : list.map((p: any) => (
          <Link key={p.id} href={`/drafts/${p.id}`} className="flex items-center gap-3 rounded-xl px-3 py-3 hover:bg-white/[0.05] transition">
            <Mail className="h-4 w-4 text-[var(--accent)] shrink-0" />
            <div className="min-w-0">
              <div className="text-[14px] text-white truncate">{p.title}</div>
              <div className="text-[12px] muted">{p.id} · approved by {p.approved_by || "staff"}{p.executed_at ? ` · ${fmtDateTime(p.executed_at)}` : ""}</div>
            </div>
            <Badge tone="amber" className="ml-auto">drafts · not sent</Badge>
          </Link>
        ))}
      </Card>
    </div>
  );
}
