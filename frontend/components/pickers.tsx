"use client";
import { X } from "lucide-react";
import { useEffect, useState } from "react";

import { Input } from "@/components/ui";
import { get } from "@/lib/api";

function useSearch(path: string, q: string) {
  const [res, setRes] = useState<any[]>([]);
  useEffect(() => {
    if (q.trim().length < 2) {
      setRes([]);
      return;
    }
    const t = setTimeout(() => get<any>(path, { q }).then((r) => setRes(r.results || [])).catch(() => setRes([])), 180);
    return () => clearTimeout(t);
  }, [path, q]);
  return res;
}

export default function LecturerPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [q, setQ] = useState(value);
  const res = useSearch("/lecturers/search", q);
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <Input value={q} onChange={(e) => { setQ(e.target.value.toUpperCase()); setOpen(true); onChange(""); }} placeholder="Lecturer id or module, e.g. MZD" onFocus={() => setOpen(true)} />
      {open && res.length > 0 && (
        <div className="absolute z-30 mt-1 w-full panel shadow-lg max-h-64 overflow-auto">
          {res.map((r) => (
            <button key={r.lecturer_id} className="block w-full text-left px-3 py-2 text-xs hover:bg-[var(--panel-2)]"
              onClick={() => { onChange(r.lecturer_id); setQ(r.lecturer_id); setOpen(false); }}>
              <b>{r.lecturer_id}</b> · {r.lecturer_name} <span className="muted">· {r.modules.slice(0, 2).join(", ")}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function MultiPicker({ kind, values, onChange, placeholder }: { kind: "lecturers" | "intakes"; values: string[]; onChange: (v: string[]) => void; placeholder: string }) {
  const [q, setQ] = useState("");
  const res = useSearch(`/${kind}/search`, q);
  return (
    <div>
      <div className="flex flex-wrap gap-1 mb-1.5">
        {values.map((v) => (
          <span key={v} className="inline-flex items-center gap-1 rounded-md bg-[var(--accent-soft)] text-[var(--accent)] text-xs px-1.5 py-0.5">
            {v}<button onClick={() => onChange(values.filter((x) => x !== v))}><X className="h-3 w-3" /></button>
          </span>
        ))}
      </div>
      <div className="relative">
        <Input value={q} onChange={(e) => setQ(e.target.value.toUpperCase())} placeholder={placeholder} />
        {res.length > 0 && (
          <div className="absolute z-30 mt-1 w-full panel shadow-lg max-h-56 overflow-auto">
            {res.map((r) => {
              const id = kind === "lecturers" ? r.lecturer_id : r.intake;
              return (
                <button key={id} className="block w-full text-left px-3 py-1.5 text-xs hover:bg-[var(--panel-2)]"
                  onClick={() => { if (!values.includes(id)) onChange([...values, id]); setQ(""); }}>
                  <b>{id}</b> {kind === "lecturers" ? <>· {r.lecturer_name} <span className="muted">· {r.modules.slice(0, 2).join(", ")}</span></> : <span className="muted">· {r.groupings.join(", ")} · ~{r.students} students</span>}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
