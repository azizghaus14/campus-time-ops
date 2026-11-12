"use client";
import { ArrowRight, Cpu, Play } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import LecturerPicker from "@/components/pickers";
import { Orb } from "@/components/orb";
import ReplanGrid from "@/components/replan-grid";
import { Badge, Button, Card, CardHeader, Empty, ErrorBox, Input, Label, PageHeader, Select, Spinner } from "@/components/ui";
import { get, post } from "@/lib/api";
import { fmtDateTime, num } from "@/lib/format";
import { useApi } from "@/lib/use-api";

export default function Page() {
  return (
    <Suspense fallback={<Spinner />}>
      <Disruptions />
    </Suspense>
  );
}

function Disruptions() {
  const sp = useSearchParams();
  const router = useRouter();
  const id = sp.get("id");
  const { data: list, reload } = useApi<any>("/disruptions", undefined, 20000);
  return (
    <div>
      <PageHeader title="Live board" subtitle="Register a disruption, see its impact on the live timetable, and watch the solver re-plan it. The assistant and the Gemini Enterprise agents create the same disruptions." />
      <div className="grid grid-cols-1 xl:grid-cols-[340px_1fr] gap-4">
        <div className="space-y-4">
          <CreateForm onCreated={(d) => { reload(); router.push(`/disruptions?id=${d.id}`); }} />
          <Card>
            <CardHeader title="Recent" />
            {!list?.disruptions?.length ? <Empty>No disruptions yet.</Empty> : (
              <ul className="px-3 pb-3 space-y-1.5 max-h-[420px] overflow-auto">
                {list.disruptions.map((d: any) => (
                  <li key={d.id}>
                    <Link href={`/disruptions?id=${d.id}`} className={`block rounded-lg border p-2 text-xs ${d.id === id ? "border-[var(--accent)] bg-[var(--accent-soft)]" : "border-[var(--border)] hover:bg-[var(--panel-2)]"}`}>
                      <div className="flex items-center gap-1.5"><b>{d.id}</b><Badge tone="red">{d.type.replace("_", " ")}</Badge><Badge>{d.status}</Badge></div>
                      <div className="mt-1 muted">{d.headline}</div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        <div className="min-w-0">{id ? <Detail key={id} id={id} autoplan={sp.get("autoplan") === "1"} onChange={reload} /> : <Card><Empty>Create or pick a disruption, or just tell the Assistant what happened.</Empty></Card>}</div>
      </div>
    </div>
  );
}

function CreateForm({ onCreated }: { onCreated: (d: any) => void }) {
  const [type, setType] = useState("LECTURER_UNAVAILABLE");
  const [lect, setLect] = useState<string>("");
  const [rooms, setRooms] = useState("");
  const [start, setStart] = useState("2026-11-13");
  const [end, setEnd] = useState("2026-11-13");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      const scope = type === "LECTURER_UNAVAILABLE" ? { lecturer_id: lect } : type === "ROOM_UNAVAILABLE" ? { rooms: rooms.split(",").map((r) => r.trim()).filter(Boolean) } : { date: start };
      const d = await post("/disruptions", { type, scope, window: type === "HOLIDAY" ? undefined : { start, end }, reason, created_by: "dashboard" });
      onCreated(d);
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card>
      <CardHeader title="New disruption" />
      <div className="px-4 pb-4 space-y-3">
        <div>
          <Label>Type</Label>
          <Select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="LECTURER_UNAVAILABLE">Lecturer unavailable</option>
            <option value="ROOM_UNAVAILABLE">Room unavailable</option>
            <option value="HOLIDAY">Holiday (whole campus)</option>
          </Select>
        </div>
        {type === "LECTURER_UNAVAILABLE" && <div><Label>Lecturer</Label><LecturerPicker value={lect} onChange={setLect} /></div>}
        {type === "ROOM_UNAVAILABLE" && <div><Label hint="comma-separated">Rooms</Label><Input value={rooms} onChange={(e) => setRooms(e.target.value)} placeholder="B-04-03" /></div>}
        <div className="grid grid-cols-2 gap-2">
          <div><Label>{type === "HOLIDAY" ? "Date" : "From"}</Label><Input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></div>
          {type !== "HOLIDAY" && <div><Label>To (incl.)</Label><Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></div>}
        </div>
        <div><Label>Reason</Label><Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. medical leave" /></div>
        <ErrorBox error={err} />
        <Button onClick={submit} loading={busy} disabled={type === "LECTURER_UNAVAILABLE" && !lect} className="w-full">Create &amp; show impact</Button>
      </div>
    </Card>
  );
}

function Detail({ id, autoplan, onChange }: { id: string; autoplan: boolean; onChange: () => void }) {
  const { data: dis, error, loading, reload } = useApi<any>(`/disruptions/${id}`, { limit: 2000 });
  const [prop, setProp] = useState<any>(null);
  const [solving, setSolving] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [animDone, setAnimDone] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (!dis) return;
    if (dis.latest_proposal_id && !prop) get(`/proposals/${dis.latest_proposal_id}`).then(setProp).catch(() => {});
    else if (autoplan && !dis.latest_proposal_id && !started.current) {
      started.current = true;
      setTimeout(run, 900);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dis]);

  async function run() {
    setSolving(true);
    setErr(null);
    setProp(null);
    setAnimDone(false);
    try {
      const t0 = Date.now();
      const p = await post(`/disruptions/${id}/plan`, { options: {} });
      const wait = Math.max(0, 1200 - (Date.now() - t0)); // let the scan read on screen for tiny solves
      setTimeout(async () => {
        setSolving(false);
        setProp(await get(`/proposals/${p.id}`));
        reload();
        onChange();
      }, wait);
    } catch (e) {
      setErr(e);
      setSolving(false);
    }
  }

  if (loading && !dis) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  const imp = dis.impact;
  const s = prop?.summary;
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2"><Badge tone="red">{dis.type.replace("_", " ")}</Badge><span className="muted text-xs">{dis.id} · {dis.created_by} · {fmtDateTime(dis.created_at)}</span></div>
            <div className="text-lg font-semibold mt-1.5">{dis.headline}</div>
            <div className="muted text-xs mt-1">
              {dis.scope.lecturer_id && <>Lecturer <b>{dis.scope.lecturer_name}</b> ({dis.scope.lecturer_id}) · </>}
              {dis.scope.rooms && <>Rooms <b>{dis.scope.rooms.join(", ")}</b> · </>}
              Window {fmtDateTime(dis.window.start)} → {fmtDateTime(dis.window.end)} {dis.reason && <>· “{dis.reason}”</>}
            </div>
          </div>
          <div className="flex gap-2">
            {prop && <Link href={`/proposals/${prop.id}`}><Button variant="success">Review proposal {prop.id} <ArrowRight className="h-4 w-4" /></Button></Link>}
            <Button onClick={run} loading={solving} variant={prop ? "outline" : "default"}>{prop ? "Re-plan" : <><Play className="h-4 w-4" /> Run solver</>}</Button>
          </div>
        </div>
        <div className="grid grid-cols-3 md:grid-cols-6 gap-3 mt-4 text-center">
          {[["Sessions", imp.sessions], ["Intake groups", imp.intake_groups], ["Intakes", imp.intakes], ["Students", `~${num(imp.students)}`], ["Lecturers", imp.lecturers], ["Already online", imp.online_sessions]].map(([l, v]) => (
            <div key={l as string} className="rounded-lg bg-[var(--panel-2)] py-2"><div className="text-lg font-semibold tabular-nums">{v}</div><div className="muted text-[11px]">{l}</div></div>
          ))}
        </div>
      </Card>

      <Card className="p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="font-semibold text-sm flex items-center gap-2"><Orb state={solving ? "solving" : prop ? "breathing" : "working"} size={28} tint={solving ? "blue" : "violet"} /> Live re-plan</div>
          <div className="text-xs muted">
            {solving ? "OR-Tools CP-SAT solving…" : prop ? <>Solved in <b className="text-[var(--text)]">{prop.stats.total_s}s</b> ({prop.stats.status}, {prop.stats.engine}{prop.stats.decomposition ? `, ${prop.stats.decomposition}` : ""}) · {num(prop.stats.variables)} variables · clash check <b className={s.clash_check.passed ? "text-[var(--green)]" : "text-[var(--red)]"}>{s.clash_check.passed ? "PASSED" : "FAILED"}</b></> : "Press Run solver"}
          </div>
        </div>
        <ReplanGrid affected={dis.affected_sessions} moves={prop?.moves || null} unresolved={prop?.unresolved || null} solving={solving} onDone={() => setAnimDone(true)} />
        <ErrorBox error={err} />
        {prop && animDone && (
          <div className="grid md:grid-cols-5 gap-3 mt-4">
            {[["Substitute", s.substituted, "violet"], ["Rescheduled", s.rescheduled, "green"], ["Room-only swaps", s.room_only_changes, "accent"], ["Online fallback", s.placed_online, "amber"], ["Unresolved", s.unresolved, "red"]].map(([l, v, t]) => (
              <div key={l as string} className="rounded-lg border border-[var(--border)] p-2.5"><div className={`text-xl font-semibold tabular-nums text-[var(--${t})]`}>{v}</div><div className="muted text-[11px]">{l}</div></div>
            ))}
          </div>
        )}
        {prop?.bulk && animDone && s.by_school && (
          <div className="mt-4">
            <div className="text-sm font-semibold mb-2">Summary by school (faculty)</div>
            <div className="max-h-[260px] overflow-auto rounded-lg border border-[var(--border)]">
              <table className="data">
                <thead><tr><th>School</th><th>Sessions</th><th>Physical</th><th>Online</th><th>Unresolved</th><th>Students</th></tr></thead>
                <tbody>{s.by_school.map((r: any) => <tr key={r.school}><td className="font-medium">{r.school}</td><td>{r.sessions}</td><td>{r.physical}</td><td>{r.online}</td><td>{r.unresolved}</td><td>{num(r.students)}</td></tr>)}</tbody>
              </table>
            </div>
            <p className="muted text-[11px] mt-2">Evening classes ending after 19:00 cannot stay physical because of the shuttle rule (last regular LRT shuttle 19:15 − 15 min, R-SHUTTLE); they move to daytime or online.</p>
          </div>
        )}
      </Card>
    </div>
  );
}
