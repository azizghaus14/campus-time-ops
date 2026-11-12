"""State repository: disruptions, proposals, audit events, runtime holidays.

Same interface, two backends:
  - JsonStore (default, local dev / offline demo): one JSON file per collection under data/state/
  - FirestoreStore (STORE_BACKEND=firestore): Google Cloud Firestore (or the emulator via FIRESTORE_EMULATOR_HOST)
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional, Protocol

from ..config import settings

COLLECTIONS = ("disruptions", "proposals", "audit", "runtime_holidays", "counters")


class Store(Protocol):
    def put(self, collection: str, doc_id: str, doc: dict) -> None: ...
    def get(self, collection: str, doc_id: str) -> Optional[dict]: ...
    def list(self, collection: str, **where: Any) -> list[dict]: ...
    def delete(self, collection: str, doc_id: str) -> None: ...
    def clear(self) -> None: ...
    def next_id(self, prefix: str) -> str: ...


class JsonStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._mem: dict[str, dict[str, dict]] = {}
        for c in COLLECTIONS:
            p = self.root / f"{c}.json"
            self._mem[c] = json.loads(p.read_text()) if p.exists() else {}

    def _flush(self, c: str) -> None:
        p = self.root / f"{c}.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._mem[c], default=str))
        tmp.replace(p)

    def put(self, collection: str, doc_id: str, doc: dict) -> None:
        with self._lock:
            self._mem.setdefault(collection, {})[doc_id] = json.loads(json.dumps(doc, default=str))
            self._flush(collection)

    def get(self, collection: str, doc_id: str) -> Optional[dict]:
        with self._lock:
            d = self._mem.get(collection, {}).get(doc_id)
            return json.loads(json.dumps(d)) if d is not None else None

    def list(self, collection: str, **where: Any) -> list[dict]:
        with self._lock:
            docs = list(self._mem.get(collection, {}).values())
        return [json.loads(json.dumps(d)) for d in docs if all(d.get(k) == v for k, v in where.items())]

    def delete(self, collection: str, doc_id: str) -> None:
        with self._lock:
            self._mem.get(collection, {}).pop(doc_id, None)
            self._flush(collection)

    def clear(self) -> None:
        with self._lock:
            for c in COLLECTIONS:
                self._mem[c] = {}
                self._flush(c)

    def next_id(self, prefix: str) -> str:
        with self._lock:
            ctr = self._mem.setdefault("counters", {})
            n = ctr.get(prefix, {"n": 0})["n"] + 1
            ctr[prefix] = {"n": n}
            self._flush("counters")
            return f"{prefix}-{n:04d}"


class FirestoreStore:  # pragma: no cover - needs GCP / emulator
    def __init__(self) -> None:
        from google.cloud import firestore

        self._fs = firestore
        self.db = firestore.Client(project=settings.gcp_project or None)

    def put(self, collection: str, doc_id: str, doc: dict) -> None:
        self.db.collection(collection).document(doc_id).set(json.loads(json.dumps(doc, default=str)))

    def get(self, collection: str, doc_id: str) -> Optional[dict]:
        snap = self.db.collection(collection).document(doc_id).get()
        return snap.to_dict() if snap.exists else None

    def list(self, collection: str, **where: Any) -> list[dict]:
        q = self.db.collection(collection)
        for k, v in where.items():
            q = q.where(filter=self._fs.FieldFilter(k, "==", v))
        return [d.to_dict() for d in q.stream()]

    def delete(self, collection: str, doc_id: str) -> None:
        self.db.collection(collection).document(doc_id).delete()

    def clear(self) -> None:
        for c in COLLECTIONS:
            for d in self.db.collection(c).list_documents():
                d.delete()

    def next_id(self, prefix: str) -> str:
        ref = self.db.collection("counters").document(prefix)

        @self._fs.transactional
        def bump(tx):
            snap = ref.get(transaction=tx)
            n = (snap.to_dict() or {}).get("n", 0) + 1 if snap.exists else 1
            tx.set(ref, {"n": n})
            return n

        return f"{prefix}-{bump(self.db.transaction()):04d}"


_store: Optional[Store] = None
_lock = threading.Lock()


def get_store() -> Store:
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                _store = FirestoreStore() if settings.store_backend == "firestore" else JsonStore(settings.state_dir)
    return _store


def set_store(s: Optional[Store]) -> None:
    """Tests / reset hook."""
    global _store
    _store = s
