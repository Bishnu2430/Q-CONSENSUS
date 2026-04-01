from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Dict, Iterable, Iterator, Optional


def _canonical_json_bytes(obj: Any) -> bytes:
    """Serialize to canonical JSON bytes for stable hashing.

    Rules:
    - UTF-8
    - sorted keys
    - no whitespace
    - ensure_ascii=False (preserve unicode)
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(obj: Any) -> str:
    return sha256(_canonical_json_bytes(obj)).hexdigest()


@dataclass(frozen=True)
class Event:
    event_id: str
    run_id: str
    ts_unix_ms: int
    event_type: str
    payload: Dict[str, Any]
    prev_event_hash: Optional[str]
    event_hash: str

    @staticmethod
    def create(
        *,
        run_id: str,
        event_type: str,
        payload: Dict[str, Any],
        prev_event_hash: Optional[str],
        ts_unix_ms: Optional[int] = None,
        event_id: Optional[str] = None,
    ) -> "Event":
        now_ms = ts_unix_ms if ts_unix_ms is not None else int(time.time() * 1000)
        eid = event_id if event_id is not None else str(uuid.uuid4())
        unsigned = {
            "event_id": eid,
            "run_id": run_id,
            "ts_unix_ms": now_ms,
            "event_type": event_type,
            "payload": payload,
            "prev_event_hash": prev_event_hash,
        }
        eh = sha256_hex(unsigned)
        return Event(
            event_id=eid,
            run_id=run_id,
            ts_unix_ms=now_ms,
            event_type=event_type,
            payload=payload,
            prev_event_hash=prev_event_hash,
            event_hash=eh,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "ts_unix_ms": self.ts_unix_ms,
            "event_type": self.event_type,
            "payload": self.payload,
            "prev_event_hash": self.prev_event_hash,
            "event_hash": self.event_hash,
        }


class JsonlEventStore:
    """Append-only JSONL store for events.

    Files are partitioned by run_id: `<base_dir>/<run_id>.jsonl`.
    """

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self._subscribers: Dict[str, list[queue.Queue[Event]]] = {}
        self._sub_lock = threading.Lock()

    def _path(self, run_id: str) -> str:
        return os.path.join(self.base_dir, f"{run_id}.jsonl")

    def append(self, event: Event) -> None:
        path = self._path(event.run_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False))
            f.write("\n")

        with self._sub_lock:
            subs = list(self._subscribers.get(event.run_id, []))
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                # Drop if subscriber is lagging; the client can recover via /api/events.
                logging.warning(
                    f"[QUEUE_OVERFLOW] run_id={event.run_id} event_type={event.event_type} "
                    f"queue_size=2048 - subscriber lagging, events may be lost"
                )

    def iter_events(self, run_id: str) -> Iterator[Event]:
        path = self._path(run_id)
        if not os.path.exists(path):
            return iter(())
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                yield Event(
                    event_id=obj["event_id"],
                    run_id=obj["run_id"],
                    ts_unix_ms=obj["ts_unix_ms"],
                    event_type=obj["event_type"],
                    payload=obj["payload"],
                    prev_event_hash=obj.get("prev_event_hash"),
                    event_hash=obj["event_hash"],
                )

    def get_tail_hash(self, run_id: str) -> Optional[str]:
        last: Optional[Event] = None
        for last in self.iter_events(run_id):
            pass
        return last.event_hash if last else None

    def subscribe(self, run_id: str, *, max_queue_size: int = 2048) -> queue.Queue[Event]:
        q: queue.Queue[Event] = queue.Queue(maxsize=max_queue_size)
        with self._sub_lock:
            self._subscribers.setdefault(run_id, []).append(q)
        return q

    def unsubscribe(self, run_id: str, q: queue.Queue[Event]) -> None:
        with self._sub_lock:
            subs = self._subscribers.get(run_id, [])
            self._subscribers[run_id] = [s for s in subs if s is not q]
            if not self._subscribers[run_id]:
                self._subscribers.pop(run_id, None)


def compute_run_commitment(event_hashes: Iterable[str]) -> str:
    """Compute a single run commitment from ordered event hashes.

    MVP: hash the canonical JSON list of event hashes.
    """
    return sha256_hex(list(event_hashes))
