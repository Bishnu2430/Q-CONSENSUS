"""Minimal, dependency-free request guarding for the run-triggering endpoints.

`/api/run` and `/api/run_async` are the expensive, abusable surface (each
call fans out into multiple LLM calls plus quantum circuit simulation), so
they get an optional API-key check and an always-on rate limit. Everything
else (status, events, metrics, replay) stays open, matching what a
read-only dashboard needs.

The API key check is opt-in: unset API_KEY (the default) preserves today's
fully-open local/dev behavior. Set it once this is deployed somewhere
reachable beyond localhost.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict


class InMemoryRateLimiter:
    """Sliding-window rate limiter, keyed per caller (e.g. client IP).

    In-memory only: correct for a single-process deployment. Running
    multiple worker processes would need a shared backend (Redis, etc.)
    instead -- noted here rather than silently pretending this scales.
    """

    def __init__(self, *, max_requests: int, window_seconds: float):
        if max_requests < 1:
            raise ValueError("max_requests must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()
        if len(hits) >= self.max_requests:
            return False
        hits.append(now)
        return True
