#!/bin/bash
# Demo 3: Backend Logs & Event Stream Analysis
# Shows reasoning process and detailed event flow

set -e

DEMO_HEADER() {
  echo -e "\n\033[95m╔═══════════════════════════════════════════════════════════╗\033[0m"
  echo -e "\033[95m║  Q-CONSENSUS: REASONING & BACKEND LOGS ANALYSIS           ║\033[0m"
  echo -e "\033[95m╚═══════════════════════════════════════════════════════════╝\033[0m\n"
}

DEMO_HEADER

API_URL="http://localhost:8000/api"

echo "🔍 This demo shows:"
echo "   1. Event flow from a recent debate"
echo "   2. Reasoning stages and agent interactions"
echo "   3. Quantum policy execution details"
echo ""

# If no run_id passed, show how to get recent runs
if [ -z "$1" ]; then
  echo "📌 Usage: $0 <run_id>"
  echo ""
  echo "To get recent run IDs, check the events directory:"
  echo "   ls -ltr data/events/ | tail -5"
  echo ""
  echo "Or run demo_2_debate_execution.sh to get a new run_id"
  exit 0
fi

RUN_ID=$1

echo "📖 Analyzing Run: $RUN_ID"
echo ""

# Fetch events
EVENTS=$(curl -s --max-time 5 "$API_URL/events/$RUN_ID" 2>/dev/null || echo "[]")
EVENT_COUNT=$(echo "$EVENTS" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [ "$EVENT_COUNT" -eq 0 ]; then
  echo -e "\033[31m✗ No events found for run $RUN_ID\033[0m"
  exit 1
fi

echo "✓ Found $EVENT_COUNT events"
echo ""

# Display event timeline
echo "┌─ Event Timeline"
echo "│"

python3 << 'PYTHON_SCRIPT'
import json
import sys
from datetime import datetime

try:
    # Read events from stdin by making the request within Python
    import subprocess
    import os
    
    run_id = os.environ.get('RUN_ID', '')
    api_url = os.environ.get('API_URL', 'http://localhost:8000/api')
    
    if not run_id:
        print("│  (Run ID not provided)")
        sys.exit(0)
    
    response = subprocess.run(
        ['curl', '-s', f'{api_url}/events/{run_id}'],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    events = json.loads(response.stdout) if response.stdout else []
    
    if not events:
        print("│  (No events)")
        sys.exit(0)
    
    # Group events by type
    event_types = {}
    for event in events:
        et = event.get('event_type', 'unknown')
        if et not in event_types:
            event_types[et] = []
        event_types[et].append(event)
    
    # Display key events
    key_events = [
        'input_received',
        'web_context_enriched',
        'quantum_randomness',
        'quantum_scheduling',
        'quantum_weights',
        'agent_prompted',
        'llm_processing_started',
        'llm_processing_completed',
        'agent_responded',
        'consensus_started',
        'consensus_weights',
        'consensus_completed',
        'final_answer',
        'run_committed',
    ]
    
    for event_type in key_events:
        if event_type in event_types:
            count = len(event_types[event_type])
            symbol = "●"
            
            if 'quantum' in event_type:
                symbol = "⚛️"
            elif 'llm' in event_type:
                symbol = "🧠"
            elif 'consensus' in event_type:
                symbol = "🤝"
            elif 'final' in event_type:
                symbol = "✨"
            
            print(f"│  {symbol} {event_type.replace('_', ' ').title():.<45} ({count}x)")
    
    print("│")
    
except Exception as e:
    print(f"│  Error: {e}")

PYTHON_SCRIPT

echo "└─ Timeline Complete"
echo ""

# Show result
RESULT=$(curl -s --max-time 3 "$API_URL/result/$RUN_ID" 2>/dev/null || echo "{}")
FINAL_ANSWER=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('final_answer', 'N/A'))" 2>/dev/null || echo "N/A")

echo "💭 Reasoning Output:"
echo "┌─"
echo "$FINAL_ANSWER" | head -10 | while IFS= read -r line; do
  echo "│  $line"
done
echo "└─"
echo ""

# Show verification result
VERIFY=$(curl -s --max-time 3 "$API_URL/verify/$RUN_ID" 2>/dev/null || echo "{}")

echo "🔐 Verification Status:"
VERIFIED=$(echo "$VERIFY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('verified', 'unknown'))" 2>/dev/null || echo "unknown")

if [ "$VERIFIED" = "True" ] || [ "$VERIFIED" = "true" ]; then
  echo "   ✓ Debate commitment verified"
else
  echo "   ℹ Verification status: $VERIFIED"
fi

echo ""
echo "📊 Event Distribution:"

python3 << 'PYTHON_SCRIPT2'
import json
import subprocess
import os
import sys

run_id = os.environ.get('RUN_ID', '')
api_url = os.environ.get('API_URL', 'http://localhost:8000/api')

response = subprocess.run(
    ['curl', '-s', f'{api_url}/events/{run_id}'],
    capture_output=True,
    text=True,
    timeout=5
)

events = json.loads(response.stdout) if response.stdout else []

event_types = {}
for event in events:
    et = event.get('event_type', 'unknown')
    event_types[et] = event_types.get(et, 0) + 1

total = len(events)
for et, count in sorted(event_types.items(), key=lambda x: -x[1])[:8]:
    pct = (count / total * 100) if total > 0 else 0
    bar_len = int(pct / 2)
    bar = "█" * bar_len
    print(f"   {et:.<35} {count:>3} ({pct:>5.1f}%) {bar}")

PYTHON_SCRIPT2

echo ""
echo "✅ Analysis complete"
echo "   For backend logs, check: docker logs q-consensus-orchestrator"
