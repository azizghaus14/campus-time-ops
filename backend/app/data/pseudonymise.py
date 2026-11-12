"""Privacy layer. The public feed carries real staff names and usernames; nothing downstream may see them.

- NAME            -> deterministic pseudonym derived from LECTID ("Dr. Lecturer MDD")
- SAMACCOUNTNAME  -> dropped
- ROOM            -> stray non-printable / replacement characters stripped
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

PII_FIELDS_DROP = {"SAMACCOUNTNAME"}
_TITLES = ["Dr.", "Ms.", "Mr.", "Assoc. Prof.", "Ts.", "Prof."]


def pseudonym_for(lectid: str) -> str:
    h = int(hashlib.sha256(lectid.encode()).hexdigest(), 16)
    return f"{_TITLES[h % len(_TITLES)]} Lecturer {lectid}"


def clean_text(s: str) -> str:
    s = s.replace("�", "")
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")
    return re.sub(r"\s+", " ", s).strip()


def pseudonymise_row(row: dict) -> dict:
    out = {k: v for k, v in row.items() if k not in PII_FIELDS_DROP}
    out["NAME"] = pseudonym_for(str(row.get("LECTID", "UNKNOWN")))
    for k in ("ROOM", "MODULE_NAME", "INTAKE", "LECTID", "MODID", "GROUPING"):
        if isinstance(out.get(k), str):
            out[k] = clean_text(out[k])
    return out


def pseudonymise_rows(rows: list[dict]) -> list[dict]:
    return [pseudonymise_row(r) for r in rows]


def assert_no_pii(rows: list[dict], real_names: set[str] | None = None) -> None:
    for r in rows:
        if "SAMACCOUNTNAME" in r:
            raise AssertionError("SAMACCOUNTNAME present after pseudonymisation")
        if not str(r.get("NAME", "")).split(" Lecturer ")[-1] == r.get("LECTID"):
            raise AssertionError(f"NAME not pseudonymised for {r.get('LECTID')}")
        if real_names and r.get("NAME") in real_names:
            raise AssertionError("real name leaked")
