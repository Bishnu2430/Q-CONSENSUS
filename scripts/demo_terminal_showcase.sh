#!/usr/bin/env bash
set -euo pipefail

API_BASE="${QCONSENSUS_API_BASE:-http://localhost:8000/api}"
TIMEOUT_SECONDS="${QCONSENSUS_DEMO_TIMEOUT:-180}"
POLL_INTERVAL="${QCONSENSUS_DEMO_POLL_INTERVAL:-1}"
ENABLE_WEB_CONTEXT="${QCONSENSUS_ENABLE_WEB_CONTEXT:-false}"

QUERY="${1:-Is AI beneficial to society? Provide balanced pros, risks, and a practical recommendation.}"

if ! command -v curl >/dev/null 2>&1; then
  echo "[error] curl is required"
  exit 1
fi

PYTHON_CMD=()
if command -v uv >/dev/null 2>&1; then
  PYTHON_CMD=(uv run python)
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD=(python3)
else
  echo "[error] python3 or uv is required"
  exit 1
fi

py() {
  "${PYTHON_CMD[@]}" "$@"
}

json_get() {
  local key="$1"
  py -c 'import json,sys; data=json.load(sys.stdin); print(data.get(sys.argv[1], ""))' "$key"
}

print_header() {
  cat <<'EOF'

============================================================
Q-CONSENSUS Terminal Showcase
============================================================
EOF
}

print_section() {
  local title="$1"
  printf "\n--- %s ---\n" "$title"
}

print_header
echo "API: $API_BASE"
echo "Timeout: ${TIMEOUT_SECONDS}s | Poll interval: ${POLL_INTERVAL}s"
echo "Web context: $ENABLE_WEB_CONTEXT"

print_section "System Status"
STATUS_JSON="$(curl -fsS "$API_BASE/status")"
echo "CPU %: $(printf '%s' "$STATUS_JSON" | json_get cpu_percent)"
echo "Memory %: $(printf '%s' "$STATUS_JSON" | json_get mem_percent)"
echo "Agents loaded: $(printf '%s' "$STATUS_JSON" | json_get agents_loaded)"
echo "Contract anchor enabled: $(printf '%s' "$STATUS_JSON" | json_get contract_anchor_enabled)"

print_section "Start Debate Run"
REQUEST_BODY="$(py - "$QUERY" "$ENABLE_WEB_CONTEXT" <<'PY'
import json
import sys

query = sys.argv[1]
raw_flag = sys.argv[2].strip().lower()
enable_web = raw_flag in {"1", "true", "yes", "on"}

payload = {
    "query": query,
    "max_rounds": 1,
    "agent_count": 3,
    "enable_web_context": enable_web,
    "use_quantum_randomness": True,
    "use_quantum_weights": True,
    "use_quantum_scheduling": True,
}
print(json.dumps(payload))
PY
)"

RUN_JSON="$(curl -fsS -X POST "$API_BASE/run_async" -H 'Content-Type: application/json' -d "$REQUEST_BODY")"
RUN_ID="$(printf '%s' "$RUN_JSON" | json_get run_id)"

if [[ -z "$RUN_ID" ]]; then
  echo "[error] failed to start run"
  echo "Response: $RUN_JSON"
  exit 1
fi

echo "Run ID: $RUN_ID"

print_section "Live Progress"
START_TS="$(date +%s)"
LAST_STAGE=""

while true; do
  NOW_TS="$(date +%s)"
  ELAPSED=$((NOW_TS - START_TS))
  if (( ELAPSED > TIMEOUT_SECONDS )); then
    echo "[error] timeout after ${TIMEOUT_SECONDS}s"
    exit 1
  fi

  PROGRESS_JSON="$(curl -fsS "$API_BASE/run/$RUN_ID/progress" || true)"
  RESULT_JSON="$(curl -fsS "$API_BASE/result/$RUN_ID" || true)"

  if [[ -n "$PROGRESS_JSON" ]]; then
    STAGE="$(printf '%s' "$PROGRESS_JSON" | json_get current_stage)"
    AGENTS_DONE="$(printf '%s' "$PROGRESS_JSON" | json_get agents_completed)"
    AGENTS_TOTAL="$(printf '%s' "$PROGRESS_JSON" | json_get total_agents)"
    ETA="$(printf '%s' "$PROGRESS_JSON" | json_get eta_seconds)"
    if [[ "$STAGE" != "$LAST_STAGE" ]]; then
      echo "[$ELAPSED s] stage=$STAGE | agents=$AGENTS_DONE/$AGENTS_TOTAL | eta=${ETA}s"
      LAST_STAGE="$STAGE"
    fi
  fi

  if [[ -n "$RESULT_JSON" ]]; then
    STATUS="$(printf '%s' "$RESULT_JSON" | json_get status)"
    if [[ "$STATUS" == "completed" || "$STATUS" == "failed" ]]; then
      break
    fi
  fi

  sleep "$POLL_INTERVAL"
done

print_section "Final Result"
STATUS="$(printf '%s' "$RESULT_JSON" | json_get status)"
FINAL_ANSWER="$(printf '%s' "$RESULT_JSON" | json_get final_answer)"
COMMITMENT="$(printf '%s' "$RESULT_JSON" | json_get commitment)"
ANCHOR_TX="$(printf '%s' "$RESULT_JSON" | json_get anchor_tx_hash)"

echo "Status: $STATUS"
echo "Commitment: ${COMMITMENT:0:64}"
echo "Anchor TX: ${ANCHOR_TX:-none}"
echo "Answer preview:"
printf '%s\n' "$FINAL_ANSWER" | head -n 10

print_section "Reasoning/Event Stream Summary"
EVENTS_JSON="$(curl -fsS "$API_BASE/events/$RUN_ID")"
py - "$EVENTS_JSON" <<'PY'
import json
import sys

events = json.loads(sys.argv[1])
print(f"Total events: {len(events)}")

counts = {}
for e in events:
  et = e.get("event_type", "unknown")
  counts[et] = counts.get(et, 0) + 1

for et in sorted(counts):
  print(f"  {et}: {counts[et]}")

print("Recent events:")
for e in events[-8:]:
  payload = e.get("payload", {})
  agent = payload.get("agent_id")
  ridx = payload.get("round_idx")
  extra = ""
  if agent is not None:
    extra += f" agent={agent}"
  if ridx is not None:
    extra += f" round={ridx}"
  print(f"  - {e.get('event_type')}{extra}")
PY

print_section "Metrics"
METRICS_JSON="$(curl -fsS "$API_BASE/metrics")"
printf '%s' "$METRICS_JSON" | py -c '
import json,sys
m = json.load(sys.stdin)
print(json.dumps(m, indent=2))
'

print_section "Blockchain Verification"
VERIFY_JSON="$(curl -fsS "$API_BASE/verify/$RUN_ID" || true)"
if [[ -n "$VERIFY_JSON" ]]; then
  printf '%s' "$VERIFY_JSON" | py -c '
import json,sys
v = json.load(sys.stdin)
print(json.dumps(v, indent=2))
'
else
  echo "Verification endpoint unavailable"
fi

print_section "Completed"
echo "Run ID: $RUN_ID"
echo "Terminal showcase finished successfully"
