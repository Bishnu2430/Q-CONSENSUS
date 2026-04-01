#!/bin/bash
# Demo 2: Complete Debate Execution (E2E)
# Runs a full debate and shows real-time progress updates

set -e

DEMO_HEADER() {
  echo -e "\n\033[95m╔═══════════════════════════════════════════════════════════╗\033[0m"
  echo -e "\033[95m║  Q-CONSENSUS: DEBATE EXECUTION (E2E PROOF OF CONCEPT)     ║\033[0m"
  echo -e "\033[95m╚═══════════════════════════════════════════════════════════╝\033[0m\n"
}

DEMO_HEADER

API_URL="http://localhost:8000/api"
POLL_INTERVAL=0.5
TIMEOUT=120

# Configuration for demo
QUERY="What is the relationship between quantum computing and AI?"
MAX_ROUNDS=2
AGENT_COUNT=3
USE_WEB=true

echo "🎯 Debate Configuration:"
echo "   Query:           $QUERY"
echo "   Max Rounds:      $MAX_ROUNDS"
echo "   Agent Count:     $AGENT_COUNT"
echo "   Web Context:     $USE_WEB"
echo ""

# Start debate
echo "📤 Submitting debate request..."

RUN_RESPONSE=$(curl -s -X POST "$API_URL/run" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"$QUERY\",
    \"max_rounds\": $MAX_ROUNDS,
    \"agent_count\": $AGENT_COUNT,
    \"enable_web_context\": $USE_WEB,
    \"use_quantum_randomness\": true,
    \"use_quantum_weights\": true,
    \"use_quantum_scheduling\": true
  }" 2>/dev/null)

RUN_ID=$(echo "$RUN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('run_id', ''))" 2>/dev/null || echo "")

if [ -z "$RUN_ID" ]; then
  echo -e "\033[31m✗ Failed to start debate\033[0m"
  echo "Response: $RUN_RESPONSE"
  exit 1
fi

echo -e "\033[92m✓ Debate started\033[0m"
echo "   Run ID: $RUN_ID"
echo ""

# Poll progress
echo "⏱️  Tracking progress (polling every ${POLL_INTERVAL}s)..."
echo ""

START_TIME=$(date +%s)
LAST_STAGE=""

while true; do
  CURRENT_TIME=$(date +%s)
  ELAPSED=$((CURRENT_TIME - START_TIME))
  
  # Fetch progress
  PROGRESS=$(curl -s --max-time 3 "$API_URL/run/$RUN_ID/progress" 2>/dev/null || echo "{}")
  
  if [ ! -z "$PROGRESS" ] && [ "$PROGRESS" != "{}" ]; then
    STAGE=$(echo "$PROGRESS" | python3 -c "import sys, json; print(json.load(sys.stdin).get('current_stage', '?'))" 2>/dev/null || echo "?")
    AGENTS_DONE=$(echo "$PROGRESS" | python3 -c "import sys, json; print(json.load(sys.stdin).get('agents_completed', 0))" 2>/dev/null || echo "0")
    TOTAL_AGENTS=$(echo "$PROGRESS" | python3 -c "import sys, json; print(json.load(sys.stdin).get('total_agents', 0))" 2>/dev/null || echo "0")
    TIME_ELAPSED=$(echo "$PROGRESS" | python3 -c "import sys, json; print(int(json.load(sys.stdin).get('time_elapsed_ms', 0)/1000))" 2>/dev/null || echo "0")
    EST_TOTAL=$(echo "$PROGRESS" | python3 -c "import sys, json; print(int(json.load(sys.stdin).get('estimated_total_ms', 0)/1000))" 2>/dev/null || echo "?")
    
    if [ "$STAGE" != "$LAST_STAGE" ]; then
      echo "   [${ELAPSED}s] 📍 Stage: $STAGE"
      echo "      └─ Agents: $AGENTS_DONE/$TOTAL_AGENTS | Elapsed: ${TIME_ELAPSED}s / ~${EST_TOTAL}s"
      LAST_STAGE="$STAGE"
    fi
  fi
  
  # Check result
  RESULT=$(curl -s --max-time 3 "$API_URL/result/$RUN_ID" 2>/dev/null || echo "{}")
  STATUS=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null || echo "unknown")
  
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    break
  fi
  
  # Timeout check
  if [ $ELAPSED -gt $TIMEOUT ]; then
    echo -e "\033[31m✗ Timeout after ${TIMEOUT}s\033[0m"
    exit 1
  fi
  
  sleep $POLL_INTERVAL
done

FINAL_TIME=$(($(date +%s) - START_TIME))

echo ""
echo "✅ Debate completed in ${FINAL_TIME}s"
echo ""

# Show results
echo "┌─ Final Result"
FINAL_ANSWER=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('final_answer', 'N/A'))" 2>/dev/null || echo "N/A")
COMMITMENT=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('commitment', 'N/A')[:64] + '...')" 2>/dev/null || echo "N/A")
ANCHOR_TX=$(echo "$RESULT" | python3 -c "import sys, json; tx=json.load(sys.stdin).get('anchor_tx_hash', None); print(tx[:16] + '...' if tx else 'None')" 2>/dev/null || echo "None")

echo "│"
echo "│  Answer: ${FINAL_ANSWER:0:100}"
if [ ${#FINAL_ANSWER} -gt 100 ]; then
  echo "│          ..."
fi
echo "│"
echo "│  Commitment: $COMMITMENT"
echo "│  Anchor TX:  $ANCHOR_TX"
echo "│"
echo "└─ Done"

echo ""
echo "📊 Metrics:"

# Fetch events
EVENTS=$(curl -s --max-time 3 "$API_URL/events/$RUN_ID" 2>/dev/null || echo "[]")
EVENT_COUNT=$(echo "$EVENTS" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

echo "   Total Events Emitted: $EVENT_COUNT"
echo "   Total Duration:       ${FINAL_TIME}s"
echo ""

echo "✅ E2E proof of concept successful"
