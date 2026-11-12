"use client";
import { CalendarCheck, CheckCircle2, FileText, Mail, RotateCcw, ShieldCheck, XCircle } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Badge, Button, Card, CardHeader, Empty, ErrorBox, Input, Label, PageHeader, Select, Spinner } from "@/components/ui";
import { post } from "@/lib/api";
import { fmtDateTime, num } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const STATUS_TONE: Record<string, string> = { DRAFT: "amber", APPROVED: "accent", EXECUTED: "green", REJECTED: "red", SUPERSEDED: "neutral", INVALID: "red" };
const TYPE_TONE: Record<string, string> = { SUBSTITUTE: "violet", RESCHEDULE: "green", ONLINE: "amber", UNRESOLVED: "red" };

export default function ProposalPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: p, error, loading, reload } = useApi<any>(`/proposals/${id}`);
  const [approver, setApprover] = useState("Programme Leader (demo)");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [pins, setPins] = useState<Record<string, any>>({});
  const [declined, setDeclined] = useState<string[]>([]);
  const [filter, setFilter] = useState({ type: "", school: "", q: "" });

  const cite = useMemo(() => Object.fromEntries((p?.citations || []).map((c: any) => [c.id, c])), [p]);
  const moves = useMemo(() => {
    if (!p?.moves) return [];
    return p.moves.filter((m: any) => (!filter.type || m.type === filter.type) && (!filter.school || m.school === filter.school)
      && (!filter.q || `${m.module_name} ${m.lecturer_id} ${m.from.room} ${m.to.room}`.toLowerCase().includes(filter.q.toLowerCase())));
  }, [p, filter]);

  async function act(kind: string, fn: () => Promise<any>) {
    setBusy(kind);
    setErr(null);
    try {
      const r = await fn();
      if (kind === "replan" && r?.id) router.push(`/proposals/${r.id}`);
      else await reload();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(null);
    }
  }

  if (loading && !p) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  const s = p.summary || {};
  const ex = p.execution;
  const editing = Object.keys(pins).length + declined.length > 0;
  const schools = [...new Set((p.moves || []).map((m: any) => m.school))].sort() as string[];

  return (
    <div>
      <PageHeader
        title={p.title}
        subtitle={<span className="flex flex-wrap items-center gap-2"><Badge tone={STATUS_TONE[p.status]}>{p.status}</Badge><span>{p.id} v{p.version} · {p.kind} · drafted by {p.created_by} {fmtDateTime(p.created_at)}</span>
          {p.disruption_id && <Link className="text-[var(--accent)]" href={`/disruptions?id=${p.disruption_id}`}>{p.disruption_id}</Link>}
          {p.approved_by && <span>· approved by <b>{p.approved_by}</b> {fmtDateTime(p.approved_at)}</span>}</span>}
      />
      <div className="grid xl:grid-cols-[1fr_330px] gap-4">
        <div className="space-y-4 min-w-0">
          {p.kind === "REPLAN" && (
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
              {[["Sessions", s.sessions], ["Substitute", s.substituted ?? 0], ["Rescheduled", s.rescheduled ?? 0], ["Online", s.placed_online], ["Unresolved", s.unresolved], ["Students", `~${num(s.students_affected)}`]].map(([l, v]) => (
                <Card key={l as string} className="px-3 py-2.5"><div className="text-xl font-semibold tabular-nums">{v}</div><div className="muted text-[11px]">{l}</div></Card>
              ))}
            </div>
          )}
          {p.kind === "REPLAN" && (
            <Card className="px-4 py-3 text-xs flex flex-wrap gap-x-5 gap-y-1">
              <span>Solver <b>{p.stats.engine}</b> · {p.stats.status} · {p.stats.total_s}s{p.stats.decomposition ? ` · ${p.stats.decomposition}` : ""}</span>
              <span>Clash check <b className={s.clash_check?.passed ? "text-[var(--green)]" : "text-[var(--red)]"}>{s.clash_check?.passed ? "PASSED — zero group, lecturer or room clashes" : "FAILED"}</b></span>
              <span>Earliest new slot (24 h notice) {s.notice_earliest ? fmtDateTime(s.notice_earliest) : "–"}</span>
            </Card>
          )}

          {p.kind === "SLOT_BOOKING" && (
            <Card className="p-4 text-sm space-y-1">
              <div className="font-semibold">{p.summary.label}</div>
              <div className="muted text-xs">Groups: {p.booking.groups.map((g: any) => `${g.intake}/${g.grouping}`).join(", ") || "–"} · Examiners/lecturers: {p.booking.lecturer_ids.join(", ") || "–"}</div>
              {p.booking.sub_slots && <div className="text-xs">{p.booking.sub_slots.map((x: any, i: number) => <span key={i} className="mr-2 mono">#{i + 1} {x.start.slice(11, 16)}–{x.end.slice(11, 16)}</span>)}</div>}
              {p.booking.description && <div className="text-xs muted">{p.booking.description}</div>}
            </Card>
          )}

          {p.kind === "REPLAN" && (
            <Card>
              <CardHeader title={`Moves (${p.moves.length})`} subtitle="Before → after, with the rule behind each constraint. Hover a rule for its source." right={
                <div className="flex gap-2">
                  <Select value={filter.type} onChange={(e) => setFilter({ ...filter, type: e.target.value })} className="h-8 text-xs w-32"><option value="">All types</option><option>SUBSTITUTE</option><option>RESCHEDULE</option><option>ONLINE</option></Select>
                  {schools.length > 1 && <Select value={filter.school} onChange={(e) => setFilter({ ...filter, school: e.target.value })} className="h-8 text-xs w-28"><option value="">All schools</option>{schools.map((x) => <option key={x}>{x}</option>)}</Select>}
                  {p.moves.length > 20 && <Input value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.target.value })} placeholder="Search" className="h-8 text-xs w-32" />}
                </div>} />
              <div className="max-h-[620px] overflow-auto">
                <table className="data">
                  <thead><tr><th>Type</th><th>Session</th><th>Before</th><th>After</th><th>Groups</th><th className="min-w-[260px]">Why</th>{p.status === "DRAFT" && <th>Edit</th>}</tr></thead>
                  <tbody>
                    {moves.slice(0, 300).map((m: any) => (
                      <tr key={m.session_id}>
                        <td><Badge tone={TYPE_TONE[m.type]}>{m.type}</Badge>{m.change === "room-only" && <div className="text-[10px] muted mt-1">room only</div>}</td>
                        <td><div className="font-medium">{m.module_name}</div><div className="muted text-[11px]">{m.lecturer_id} · {m.school} · ~{m.students} students</div></td>
                        <td className="whitespace-nowrap text-xs">{m.from.label}<div className="muted">{m.from.room}</div></td>
                        <td className="whitespace-nowrap text-xs">
                          {m.type === "SUBSTITUTE" ? <><b className="text-[var(--violet)]">{m.substitute}</b> teaches<div className="muted">{m.substitute_name} · {m.substitute_match === "section" ? "same section" : "same module"}</div></>
                            : <><b>{m.to.label}</b><div className="muted">{m.to.room}</div></>}
                        </td>
                        <td className="text-[11px] muted max-w-[160px]">{m.affected_groups.slice(0, 4).map((g: any) => `${g.intake}/${g.grouping}`).join(", ")}{m.affected_groups.length > 4 && ` +${m.affected_groups.length - 4}`}</td>
                        <td className="text-[12px]">
                          <div>{m.rationale}</div>
                          <div className="flex flex-wrap gap-1 mt-1">{m.rule_ids.map((r: string) => <Badge key={r} tone={cite[r]?.label?.startsWith("QUOTED") ? "accent" : "neutral"} title={cite[r] ? `${cite[r].title} [${cite[r].label}] — ${cite[r].source}` : r}>{r}</Badge>)}</div>
                        </td>
                        {p.status === "DRAFT" && (
                          <td className="text-xs">
                            {m.type === "SUBSTITUTE" ? (
                              <label className="flex items-center gap-1 whitespace-nowrap"><input type="checkbox" checked={declined.includes(m.session_id)} onChange={(e) => setDeclined(e.target.checked ? [...declined, m.session_id] : declined.filter((x) => x !== m.session_id))} /> decline sub</label>
                            ) : (
                              <Select className="h-7 text-xs w-28" value={pins[m.session_id]?.period || ""} onChange={(e) => {
                                const v = e.target.value; const n = { ...pins };
                                if (v) n[m.session_id] = { period: v }; else delete n[m.session_id];
                                setPins(n);
                              }}>
                                <option value="">keep</option><option value="morning">morning</option><option value="afternoon">afternoon</option>
                              </Select>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {moves.length > 300 && <div className="muted text-xs p-3">Showing 300 of {moves.length}. Filter by school or type to see the rest.</div>}
              </div>
            </Card>
          )}

          {p.unresolved?.length > 0 && (
            <Card>
              <CardHeader title={`Unresolved (${p.unresolved.length})`} subtitle="Never silently dropped (R-UNRESOLVED)" />
              <ul className="px-4 pb-4 space-y-2 text-sm">
                {p.unresolved.map((u: any, i: number) => (
                  <li key={i} className="rounded-lg border border-[var(--red)]/30 bg-[var(--red-soft)] p-2.5">
                    <b>{u.session.module_name}</b> <span className="muted text-xs">{u.session.date} {u.session.time} {u.session.room} · {u.session.lecturer_id}</span>
                    <div className="text-xs mt-1">{u.reason}</div>
                    {u.options?.length > 0 && <div className="text-xs muted mt-1">Options: {u.options.join(" · ")}</div>}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card className="p-4 xl:sticky xl:top-16">
            <div className="font-semibold text-sm flex items-center gap-2"><ShieldCheck className="h-4 w-4" /> Human approval</div>
            <p className="muted text-xs mt-1">Nothing changes until a person approves. Execution creates Calendar events, Gmail <b>drafts</b> (a human sends them) and a change-log entry.</p>
            <ErrorBox error={err} />
            {p.status === "DRAFT" && (
              <div className="space-y-3 mt-3">
                {editing && (
                  <div className="rounded-lg bg-[var(--accent-soft)] p-2.5 text-xs">
                    <b>{Object.keys(pins).length + declined.length} edit(s)</b> — re-planning creates v{p.version + 1} and supersedes this draft.
                    <Button size="sm" className="w-full mt-2" loading={busy === "replan"} onClick={() => act("replan", () => post(`/disruptions/${p.disruption_id}/plan`, { options: { ...p.options, pins: { ...(p.options?.pins || {}), ...pins }, decline_substitutes: [...(p.options?.decline_substitutes || []), ...declined] } }))}>
                      <RotateCcw className="h-3.5 w-3.5" /> Re-plan with edits
                    </Button>
                  </div>
                )}
                <div><Label>Approver</Label><Input value={approver} onChange={(e) => setApprover(e.target.value)} /></div>
                <Button variant="success" className="w-full" disabled={editing} loading={busy === "approve"} onClick={() => act("approve", () => post(`/proposals/${p.id}/approve`, { approver }))}>
                  <CheckCircle2 className="h-4 w-4" /> Approve
                </Button>
                <div className="flex gap-2">
                  <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (optional)" />
                  <Button variant="outline" loading={busy === "reject"} onClick={() => act("reject", () => post(`/proposals/${p.id}/reject`, { reason }))}><XCircle className="h-4 w-4" /> Reject</Button>
                </div>
              </div>
            )}
            {p.status === "APPROVED" && (
              <div className="mt-3 space-y-2">
                <div className="text-xs">Approved by <b>{p.approved_by}</b>. Ready to execute.</div>
                <Button className="w-full" loading={busy === "exec"} onClick={() => act("exec", () => post(`/proposals/${p.id}/execute`))}>
                  <CalendarCheck className="h-4 w-4" /> Execute: Calendar + Gmail drafts + change log
                </Button>
              </div>
            )}
            {p.status === "EXECUTED" && ex && (
              <div className="mt-3 space-y-2 text-sm">
                <div className="flex items-center gap-2 text-[var(--green)] font-medium"><CheckCircle2 className="h-4 w-4" /> Executed {fmtDateTime(p.executed_at)}</div>
                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="rounded-lg bg-[var(--panel-2)] py-2"><div className="text-lg font-semibold">{ex.actions.calendar_events ?? 0}</div>events</div>
                  <div className="rounded-lg bg-[var(--panel-2)] py-2"><div className="text-lg font-semibold">{ex.actions.gmail_drafts ?? 0}</div>drafts</div>
                  <div className="rounded-lg bg-[var(--panel-2)] py-2"><div className="text-lg font-semibold">{ex.actions.changelog_entries ?? 0}</div>log entry</div>
                </div>
                <div className="text-[11px] muted">Workspace mode: <b>{ex.mode}</b></div>
                {ex.calendar?.bundle_url && <a className="flex items-center gap-2 text-[var(--accent)] text-xs" href={ex.calendar.bundle_url} target="_blank"><CalendarCheck className="h-3.5 w-3.5" /> All calendar events (.ics)</a>}
                {ex.drafts?.index_url && <a className="flex items-center gap-2 text-[var(--accent)] text-xs" href={ex.drafts.index_url} target="_blank"><Mail className="h-3.5 w-3.5" /> Gmail drafts index</a>}
                {ex.changelog?.doc_url && <a className="flex items-center gap-2 text-[var(--accent)] text-xs" href={ex.changelog.doc_url} target="_blank"><FileText className="h-3.5 w-3.5" /> Timetable Change Log</a>}
                <details className="text-xs"><summary className="cursor-pointer muted">Drafts ({ex.drafts?.count})</summary>
                  <ul className="mt-1 space-y-1">{ex.drafts?.drafts?.map((d: any) => <li key={d.id}><a className="text-[var(--accent)]" href={d.url} target="_blank">{d.subject}</a> <span className="muted">→ {d.to.join(", ")}</span></li>)}</ul>
                </details>
                <details className="text-xs"><summary className="cursor-pointer muted">Calendar events ({ex.calendar?.count})</summary>
                  <ul className="mt-1 space-y-1">{ex.calendar?.events?.map((e: any, i: number) => <li key={i}><a className="text-[var(--accent)]" href={e.url} target="_blank">{e.summary}</a> <span className="muted">{fmtDateTime(e.start)}</span></li>)}</ul>
                </details>
              </div>
            )}
            {(p.status === "REJECTED" || p.status === "SUPERSEDED") && <div className="text-xs mt-3 muted">This proposal is {p.status.toLowerCase()}{p.rejected_reason ? `: ${p.rejected_reason}` : ""}.</div>}
          </Card>
          <Card>
            <CardHeader title="Rules cited" subtitle="QUOTED = APU documents · ASSUMPTION = prototype rule" />
            {!p.citations?.length ? <Empty>None</Empty> : (
              <ul className="px-4 pb-4 space-y-2">
                {p.citations.map((c: any) => (
                  <li key={c.id} className="text-xs">
                    <div className="flex items-center gap-1.5"><Badge tone={c.label.startsWith("QUOTED") ? "accent" : "neutral"}>{c.id}</Badge><b>{c.title}</b></div>
                    <div className="muted mt-0.5">[{c.label}] {c.source}</div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
