#!/usr/bin/env python3
"""Live end-to-end API validation for Q-CONSENSUS.

This script targets a running server (default: http://localhost:8000/api)
and verifies the core paths used by the frontend:
- system status
- async run + progress polling
- event stream availability
- final result + commitment
- metrics endpoint
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


BASE_URL = os.getenv("QCONSENSUS_API_BASE", "http://localhost:8000/api").rstrip("/")
TIMEOUT_SECONDS = int(os.getenv("QCONSENSUS_E2E_TIMEOUT", "150"))
POLL_INTERVAL_SECONDS = float(os.getenv("QCONSENSUS_E2E_POLL_INTERVAL", "0.8"))


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _request_json(method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 20) -> tuple[int, Any]:
    url = f"{BASE_URL}{path}"
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {"error": raw}
        except json.JSONDecodeError:
            parsed = {"error": raw}
        return exc.code, parsed


def check_status() -> CheckResult:
    code, data = _request_json("GET", "/status", timeout=8)
    if code != 200:
        return CheckResult("status", False, f"GET /status returned {code}: {data}")

    required = ["cpu_percent", "mem_percent", "agents_loaded"]
    missing = [k for k in required if k not in (data or {})]
    if missing:
        return CheckResult("status", False, f"Missing fields in /status: {missing}")

    return CheckResult(
        "status",
        True,
        f"OK (agents_loaded={data.get('agents_loaded')}, cpu={data.get('cpu_percent')}%, mem={data.get('mem_percent')}%)",
    )


def check_async_run_flow() -> CheckResult:
    start_payload = {
        "query": "Is AI beneficial to society? Provide balanced pros, risks, and a practical recommendation.",
        "max_rounds": 1,
        "agent_count": 3,
        "enable_web_context": False,
        "use_quantum_randomness": True,
        "use_quantum_weights": True,
        "use_quantum_scheduling": True,
    }

    code, started = _request_json("POST", "/run_async", payload=start_payload, timeout=15)
    if code != 200:
        return CheckResult("async_run", False, f"POST /run_async returned {code}: {started}")

    run_id = (started or {}).get("run_id")
    if not run_id:
        return CheckResult("async_run", False, f"No run_id in /run_async response: {started}")

    seen_stages: set[str] = set()
    last_progress: dict[str, Any] | None = None
    deadline = time.time() + TIMEOUT_SECONDS

    while time.time() < deadline:
        p_code, progress = _request_json("GET", f"/run/{run_id}/progress", timeout=8)
        if p_code == 200 and isinstance(progress, dict):
            last_progress = progress
            stage = progress.get("current_stage")
            if isinstance(stage, str):
                seen_stages.add(stage)

        r_code, result = _request_json("GET", f"/result/{run_id}", timeout=8)
        if r_code == 200 and isinstance(result, dict):
            status = result.get("status")
            if status == "completed":
                commitment = result.get("commitment")
                final_answer = result.get("final_answer")
                if not commitment or not final_answer:
                    return CheckResult(
                        "async_run",
                        False,
                        f"Completed run missing commitment/final_answer: {result}",
                    )

                expected_progress_fields = [
                    "current_stage",
                    "stage_progress",
                    "agents_completed",
                    "time_elapsed_ms",
                    "estimated_total_ms",
                ]
                if not last_progress:
                    return CheckResult("async_run", False, "No progress payload observed during run")
                missing = [k for k in expected_progress_fields if k not in last_progress]
                if missing:
                    return CheckResult("async_run", False, f"Progress payload missing fields: {missing}")

                e_code, events = _request_json("GET", f"/events/{run_id}", timeout=8)
                if e_code != 200 or not isinstance(events, list):
                    return CheckResult("async_run", False, f"Failed to fetch events for run_id={run_id}")

                event_types = {e.get("event_type") for e in events if isinstance(e, dict)}
                required_events = {"input_received", "agent_responded", "final_answer", "run_committed"}
                if not required_events.issubset(event_types):
                    return CheckResult(
                        "async_run",
                        False,
                        f"Missing required event types: {sorted(required_events - event_types)}",
                    )

                m_code, metrics = _request_json("GET", "/metrics", timeout=8)
                if m_code != 200 or not isinstance(metrics, dict):
                    return CheckResult("async_run", False, "GET /metrics failed after completed run")

                return CheckResult(
                    "async_run",
                    True,
                    (
                        f"OK (run_id={run_id}, stages={sorted(seen_stages)}, "
                        f"events={len(events)}, commitment={str(commitment)[:16]}...)"
                    ),
                )

            if status == "failed":
                return CheckResult("async_run", False, f"Run failed: {result}")

        time.sleep(POLL_INTERVAL_SECONDS)

    return CheckResult(
        "async_run",
        False,
        f"Timed out after {TIMEOUT_SECONDS}s waiting for completion. Last progress={last_progress}",
    )


def main() -> int:
    print(f"Running Q-CONSENSUS E2E checks against {BASE_URL}")
    checks = [check_status(), check_async_run_flow()]

    for item in checks:
        mark = "PASS" if item.passed else "FAIL"
        print(f"[{mark}] {item.name}: {item.detail}")

    failed = [c for c in checks if not c.passed]
    if failed:
        print(f"\nE2E failed ({len(failed)}/{len(checks)} checks failed)")
        return 1

    print(f"\nE2E passed ({len(checks)}/{len(checks)} checks passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
