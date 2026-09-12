"""Startup reconciliation for the event store.

A run's event file can stop mid-stream with no terminal event at all if the
process is killed while a request is in flight (a container restart during
a debate round, for example) -- the JSONL file just stops after
`agent_prompted` or `llm_processing_started`, with nothing recording *why*.
Left alone, these runs stay ambiguous forever: replay, `/api/result`, and
metrics have no way to tell "still running" apart from "died and nobody
will ever finish it".

This scans every run on startup and appends a `run_crashed` event to any
run whose event file doesn't end in a real terminal event, so downstream
consumers see an explicit, closed-out state instead of silent truncation.
Idempotent: a run already ending in `run_committed` or `run_crashed` is
left untouched.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from .events import Event, JsonlEventStore

logger = logging.getLogger(__name__)

_TERMINAL_EVENT_TYPES = {"run_committed", "run_crashed"}


@dataclass(frozen=True)
class ReconcileReport:
    total_runs: int
    already_complete: int
    marked_crashed: int
    crashed_run_ids: List[str] = field(default_factory=list)


def reconcile_incomplete_runs(store: JsonlEventStore) -> ReconcileReport:
    run_ids = store.list_run_ids()
    already_complete = 0
    crashed_run_ids: List[str] = []

    for run_id in run_ids:
        try:
            events = list(store.iter_events(run_id))
            if not events:
                continue

            last_event = events[-1]
            if last_event.event_type in _TERMINAL_EVENT_TYPES:
                already_complete += 1
                continue

            crash_event = Event.create(
                run_id=run_id,
                event_type="run_crashed",
                payload={
                    "reason": "no terminal event found on startup reconciliation",
                    "last_event_type": last_event.event_type,
                    "event_count": len(events),
                },
                prev_event_hash=last_event.event_hash,
            )
            store.append(crash_event)
            crashed_run_ids.append(run_id)
            logger.warning(
                "[RECONCILE] run_id=%s last_event_type=%s event_count=%d - marked run_crashed",
                run_id,
                last_event.event_type,
                len(events),
            )
        except Exception:
            # Reconciliation is a best-effort startup nicety; a single
            # unreadable/unwritable run file (e.g. permission mismatch from
            # a container that wrote it as a different user) must never
            # block the app from starting.
            logger.exception("[RECONCILE] run_id=%s - failed to reconcile, skipping", run_id)

    report = ReconcileReport(
        total_runs=len(run_ids),
        already_complete=already_complete,
        marked_crashed=len(crashed_run_ids),
        crashed_run_ids=crashed_run_ids,
    )
    logger.info(
        "[RECONCILE] total_runs=%d already_complete=%d marked_crashed=%d",
        report.total_runs,
        report.already_complete,
        report.marked_crashed,
    )
    return report
