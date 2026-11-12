"""Rule registry parsed from grounding/campus_ops_policy.md (single source of truth for rule ids + labels)."""
from __future__ import annotations

import re
from functools import lru_cache

from ..config import settings

_H = re.compile(r"^###\s+(R-[A-Z0-9-]+):\s*(.+?)\s*\[([^\]]+)\]\s*$")


@lru_cache(maxsize=1)
def rules() -> dict[str, dict]:
    path = settings.grounding_dir / "campus_ops_policy.md"
    out: dict[str, dict] = {}
    cur = None
    for line in path.read_text().splitlines():
        m = _H.match(line)
        if m:
            cur = m.group(1)
            out[cur] = {"id": cur, "title": m.group(2), "label": m.group(3), "text": "", "source": "grounding/campus_ops_policy.md"}
            continue
        if line.startswith("## ") or line.startswith("### "):
            cur = None
        elif cur:
            out[cur]["text"] += line.strip() + " "
    for r in out.values():
        r["text"] = r["text"].strip()
        src = re.search(r"\((HB|HOL|SHUTTLE)[^)]*\)", r["text"])
        if src:
            r["source"] = src.group(0).strip("()")
    return out


def cite(ids: list[str]) -> list[dict]:
    rs = rules()
    seen, out = set(), []
    for i in ids:
        if i in rs and i not in seen:
            seen.add(i)
            r = rs[i]
            out.append({"id": i, "title": r["title"], "label": r["label"], "source": r["source"], "excerpt": r["text"][:280]})
    return out


def get_policy() -> dict:
    return {"rules": list(rules().values()), "thresholds": {
        "attendance_threshold": settings.attendance_threshold,
        "notice_hours": settings.notice_hours,
        "shuttle_buffer_min": settings.shuttle_buffer_min,
        "shuttle_include_limited": settings.shuttle_include_limited,
    }}
