"use client";
// Readable view of the Gmail drafts one approval wrote (the .eml files in the outbox), instead of raw JSON / downloads.
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, CheckCircle2, Download, Mail, Send } from "lucide-react";

import { Badge, Card, Empty, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { post } from "@/lib/api";
import { useApi } from "@/lib/use-api";

type Draft = { id: string; file: string; from: string; to: string; subject: string; body: string };

// minimal RFC 822 + quoted-printable reader (our own plain-text drafts)
function parseEml(raw: string): Omit<Draft, "id" | "file"> {
  const text = raw.replace(/\r\n/g, "\n");
  const cut = text.indexOf("\n\n");
  const head = text.slice(0, cut < 0 ? text.length : cut).replace(/\n[ \t]+/g, " ");
  let body = cut < 0 ? "" : text.slice(cut + 2);
  const h = (k: string) => head.match(new RegExp(`^${k}:\\s*(.*)$`, "im"))?.[1]?.trim() || "";
  if (/quoted-printable/i.test(h("Content-Transfer-Encoding"))) {
    const bytes = body.replace(/=\n/g, "").replace(/=([0-9A-F]{2})/gi, (_, x) => String.fromCharCode(parseInt(x, 16)));
    try { body = decodeURIComponent(escape(bytes)); } catch { body = bytes; }
  }
  return { from: h("From"), to: h("To"), subject: h("Subject"), body: body.trim() };
}

export default function Drafts() {
  const { id } = useParams<{ id: string }>();
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [error, setError] = useState<any>(null);
  const [open, setOpen] = useState(0);
  const { data: sentInfo, reload } = useApi<any>(`/outbox/${id}/sent`);
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState<any>(null);
  const sent = (sentInfo?.sent || {}) as Record<string, any>;
  const sendIt = async (file: string) => {
    setSending(true); setSendErr(null);
    try { await post(`/outbox/${id}/drafts/${file}/send`); await reload?.(); } catch (e) { setSendErr(e); } finally { setSending(false); }
  };
  const sendAll = async () => {
    const todo = (drafts || []).filter((d) => !sent[d.file]);
    if (!todo.length || !window.confirm(`Send ${todo.length} email${todo.length > 1 ? "s" : ""}? Review them first: this sends every draft not yet sent.`)) return;
    setSending(true); setSendErr(null);
    try { for (const d of todo) await post(`/outbox/${id}/drafts/${d.file}/send`); } catch (e) { setSendErr(e); }
    finally { await reload?.(); setSending(false); }
  };
  const unsent = (drafts || []).filter((d) => !sent[d.file]).length;

  useEffect(() => {
    (async () => {
      try {
        const idx = await fetch(`/outbox/${id}/drafts_index.json`).then((r) => { if (!r.ok) throw new Error("No drafts for this plan (was the demo reset?)"); return r.json(); });
        const list = await Promise.all((idx as any[]).map(async (d) => {
          const file = String(d.url).split("/").pop();
          const raw = await fetch(`/outbox/${id}/drafts/${file}`).then((r) => r.text());
          return { id: d.id, file: String(file), ...parseEml(raw) };
        }));
        setDrafts(list);
        const i = Number(new URLSearchParams(window.location.search).get("i"));
        if (i > 0 && i < list.length) setOpen(i);
      } catch (e) { setError(e); }
    })();
  }, [id]);

  if (!drafts && !error) return <Spinner />;
  const cur = drafts?.[open];
  return (
    <div>
      <Link href="/drafts" className="inline-flex items-center gap-1.5 text-[12.5px] muted hover:text-white mb-3"><ArrowLeft className="h-3.5 w-3.5" /> All email drafts</Link>
      <PageHeader title={`Email drafts · ${id}`}
        subtitle="Written after a person approved the plan. Nothing is sent automatically: a person reviews each email and presses Send." />
      <ErrorBox error={error} />
      {drafts && drafts.length > 0 && (
        <div className="flex items-center gap-3 mb-4">
          <span className="text-[13px] muted">{drafts.length - unsent} of {drafts.length} sent</span>
          {unsent > 0 ? (
            <button onClick={sendAll} disabled={sending}
              className="inline-flex items-center gap-1.5 rounded-full bg-[var(--green)] px-4 py-1.5 text-[13px] font-semibold text-black hover:opacity-90 disabled:opacity-50">
              <Send className="h-3.5 w-3.5" /> {sending ? "Sending…" : `Send all (${unsent})`}</button>
          ) : <Badge tone="green">All sent{sentInfo?.mode === "smtp" ? "" : " · demo mode, not delivered"}</Badge>}
        </div>
      )}
      {drafts && !drafts.length && <Card><Empty>No drafts.</Empty></Card>}
      {drafts && drafts.length > 0 && (
        <div className="grid gap-4 md:grid-cols-[minmax(260px,360px)_1fr]">
          <Card className="p-2 max-h-[70vh] overflow-auto">
            {drafts.map((d, i) => (
              <button key={d.id} onClick={() => setOpen(i)}
                className={`w-full text-left rounded-xl px-3 py-2.5 transition ${i === open ? "bg-white/[0.08]" : "hover:bg-white/[0.04]"}`}>
                <div className="flex items-center gap-2 text-[13px] text-white">{sent[d.file] ? <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-[var(--green)]" /> : <Mail className="h-3.5 w-3.5 shrink-0 text-[var(--accent)]" />}<span className="truncate">{d.subject}</span></div>
                <div className="text-[11.5px] muted truncate mt-0.5 pl-5">{d.to}</div>
              </button>
            ))}
          </Card>
          {cur && (
            <Card className="p-6">
              <div className="flex flex-wrap items-center gap-2 mb-4">
                {sent[cur.file]
                  ? <Badge tone="green">{sent[cur.file].mode === "smtp" ? "Sent" : "Sent · demo mode, not delivered"}</Badge>
                  : <Badge tone="amber">Draft · not sent</Badge>}
                <span className="text-[12px] muted">{open + 1} of {drafts.length}</span>
                <span className="ml-auto flex gap-2">
                  {!sent[cur.file] && (
                    <button onClick={() => sendIt(cur.file)} disabled={sending}
                      className="inline-flex items-center gap-1.5 rounded-full bg-[var(--green)] px-3.5 py-1.5 text-[12.5px] font-semibold text-black hover:opacity-90 disabled:opacity-50">
                      <Send className="h-3.5 w-3.5" /> {sending ? "Sending…" : "Send"}</button>
                  )}
                  {/* a person sends it: Gmail opens a filled-in compose window; nothing is sent until they press Send there */}
                  <a target="_blank" rel="noreferrer"
                    href={`https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(cur.to)}&su=${encodeURIComponent(cur.subject)}&body=${encodeURIComponent(cur.body)}`}
                    className="inline-flex items-center gap-1.5 rounded-full border border-white/15 px-3 py-1.5 text-[12.5px] muted hover:text-white">
                    <Mail className="h-3.5 w-3.5" /> Open in Gmail</a>
                  <a href={`/outbox/${id}/drafts/${cur.file}`} download
                    className="inline-flex items-center gap-1.5 rounded-full border border-white/15 px-3 py-1.5 text-[12.5px] muted hover:text-white">
                    <Download className="h-3.5 w-3.5" /> .eml</a>
                </span>
              </div>
              <ErrorBox error={sendErr} />
              {sent[cur.file] && (
                <div className="flex items-center gap-2 text-[12.5px] text-[var(--green)] mb-4">
                  <CheckCircle2 className="h-4 w-4" /> Sent by {sent[cur.file].sent_by}
                  {sent[cur.file].mode === "smtp" ? "" : " · demo mode: recorded in the audit log, no email delivered"}
                </div>
              )}
              <div className="text-[13px] space-y-1 mb-5">
                <div><span className="muted inline-block w-16">From</span>{cur.from}</div>
                <div><span className="muted inline-block w-16">To</span>{cur.to}</div>
                <div className="text-[18px] font-semibold text-white pt-2">{cur.subject}</div>
              </div>
              <div className="whitespace-pre-wrap text-[14px] leading-relaxed text-white/85 border-t border-white/10 pt-5">{cur.body}</div>
            </Card>
          )}
        </div>
      )}
      <p className="text-[12px] muted mt-4"><Link className="text-[var(--accent)]" href={`/proposals/${id}`}>Full plan {id}</Link> · demo recipients are placeholder addresses</p>
    </div>
  );
}
