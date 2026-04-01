#!/bin/bash
# Demo 1: System Status & Resource Summary
# Shows backend readiness and resource allocation

set -e

DEMO_HEADER() {
  echo -e "\n\033[95m╔═══════════════════════════════════════════════════════════╗\033[0m"
  echo -e "\033[95m║  Q-CONSENSUS: SYSTEM STATUS & PERFORMANCE                  ║\033[0m"
  echo -e "\033[95m╚═══════════════════════════════════════════════════════════╝\033[0m\n"
}

DEMO_HEADER

API_URL="http://localhost:8000/api"
TIMEOUT=5

echo "📊 Fetching system status from backend..."
echo "   Endpoint: GET $API_URL/status"

STATUS=$(curl -s --max-time $TIMEOUT "$API_URL/status" 2>/dev/null || echo "{}")

if [ -z "$STATUS" ] || [ "$STATUS" = "{}" ]; then
  echo -e "\033[31m✗ Backend not responding\033[0m"
  echo "   Make sure backend is running: python -m src.qconsensus.web"
  exit 1
fi

echo -e "\033[92m✓ Backend Connected\033[0m\n"

# Parse JSON response
CPU=$(echo "$STATUS" | python3 -c "import sys, json; print(json.load(sys.stdin).get('cpu_percent', 'N/A'))" 2>/dev/null || echo "N/A")
MEM_TOTAL=$(echo "$STATUS" | python3 -c "import sys, json; d=json.load(sys.stdin); print(f\"{d.get('mem_used', 0)}/{d.get('mem_total', 0)} MB\")" 2>/dev/null || echo "N/A")
MEM_PCT=$(echo "$STATUS" | python3 -c "import sys, json; print(json.load(sys.stdin).get('mem_percent', 'N/A'))" 2>/dev/null || echo "N/A")
AGENTS=$(echo "$STATUS" | python3 -c "import sys, json; print(json.load(sys.stdin).get('agents_loaded', 'N/A'))" 2>/dev/null || echo "N/A")
ANCHOR=$(echo "$STATUS" | python3 -c "import sys, json; print(json.load(sys.stdin).get('contract_anchor_enabled', False))" 2>/dev/null || echo "N/A")

echo "┌─ System Resources"
echo "│"
echo "│  CPU Usage:           $CPU %"
echo "│  Memory:              $MEM_TOTAL ($MEM_PCT %)"
echo "│  Agents Loaded:       $AGENTS"
echo "│  Blockchain Anchor:   $ANCHOR"
echo "│"
echo "└─ Backend Ready: ✓"

echo ""
echo "📈 Healthcare Indicators:"

# Calculate severity
if (( $(echo "$CPU > 80" | bc -l 2>/dev/null || echo 0) )); then
  echo "   ⚠️  High CPU usage - consider reducing concurrent runs"
fi

if (( $(echo "$MEM_PCT > 85" | bc -l 2>/dev/null || echo 0) )); then
  echo "   ⚠️  High memory usage - system operating near capacity"
fi

if [ "$AGENTS" -lt 2 ]; then
  echo "   ⚠️  Agent roster not loaded - check config/agents.yaml"
fi

if [ "$AGENTS" -ge 2 ]; then
  echo "   ✓ Agent roster ready for debates"
fi

echo ""
echo "✅ System status retrieved successfully"
echo "   Ready to proceed with debate execution"
