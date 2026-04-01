#!/bin/bash
# MASTER DEMO SCRIPT
# Orchestrates all 3 demos for a complete E2E proof of concept
# Usage: ./demo_all.sh [run_existing_id]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="$PROJECT_ROOT/demo_run_$(date +%Y%m%d_%H%M%S).log"

# Configuration
DEMO_DELAY=2
PAUSE_BETWEEN_DEMOS=3

MASTER_HEADER() {
  cat << 'EOF'

████████████████████████████████████████████████████████████████████████████████
██                                                                              ██
██  ███████╗ █████╗ ██╗      █████╗ ██╗ ██╗     ██╗      █████╗ ██╗  ██╗      ██
██  ██╔════╝██╔══██╗██║     ██╔══██╗██║ ╚██╗   ██╔╝     ██╔══██╗██║  ██║      ██
██  █████╗  ███████║██║     ███████║██║  ╚████╔╝      ███████║███████║      ██
██  ██╔══╝  ██╔══██║██║     ██╔══██║██║   ╚██╔╝       ██╔══██║██╔══██║      ██
██  ███████╗██║  ██║███████╗██║  ██║██║    ██║        ██║  ██║██║  ██║      ██
██  ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝    ╚═╝        ╚═╝  ╚═╝╚═╝  ╚═╝      ██
██                                                                              ██
██            Q-CONSENSUS DEMO: REAL-TIME DEBATE WITH QUANTUM FEATURES        ██
██                                                                              ██
████████████████████████████████████████████████████████████████████████████████

EOF
}

LOG() {
  echo "$1"
  echo "$1" >> "$LOG_FILE"
}

DEMO_SECTION() {
  echo ""
  echo "╔════════════════════════════════════════════════════════════════╗"
  echo "║  $1"
  echo "╚════════════════════════════════════════════════════════════════╝"
  echo ""
}

# Main
MASTER_HEADER

LOG "=== Q-CONSENSUS DEMO ==="
LOG "Started: $(date)"
LOG "Log file: $LOG_FILE"
LOG ""

# Check prerequisites
LOG "🔍 Checking prerequisites..."

if ! command -v curl &> /dev/null; then
  LOG "✗ curl not found"
  exit 1
fi

if ! command -v python3 &> /dev/null; then
  LOG "✗ python3 not found"
  exit 1
fi

LOG "✓ Prerequisites met"
LOG ""

# Demo 1: System Status
DEMO_SECTION "DEMO 1/3: System Status & Resources"

LOG "[$(date '+%H:%M:%S')] Running system status check..."
if [ -f "$SCRIPT_DIR/demo_1_system_status.sh" ]; then
  bash "$SCRIPT_DIR/demo_1_system_status.sh" 2>&1 | tee -a "$LOG_FILE"
  STATUS_EXIT=${PIPESTATUS[0]}
  if [ $STATUS_EXIT -ne 0 ]; then
    LOG "✗ Demo 1 failed"
    exit 1
  fi
else
  LOG "✗ demo_1_system_status.sh not found"
  exit 1
fi

read -p "Press Enter to continue to Demo 2..." < /dev/tty
echo ""

# Demo 2: Debate Execution
DEMO_SECTION "DEMO 2/3: Complete Debate Execution (E2E)"

LOG "[$(date '+%H:%M:%S')] Running debate execution..."
if [ -f "$SCRIPT_DIR/demo_2_debate_execution.sh" ]; then
  # Run and capture run_id
  DEMO_OUTPUT=$(bash "$SCRIPT_DIR/demo_2_debate_execution.sh" 2>&1 | tee -a "$LOG_FILE")
  
  # Extract run_id from output
  RUN_ID=$(echo "$DEMO_OUTPUT" | grep "Run ID:" | head -1 | awk '{print $NF}')
  
  if [ -z "$RUN_ID" ]; then
    LOG "⚠ Could not extract run_id from demo output"
    RUN_ID=""
  else
    LOG "Captured Run ID: $RUN_ID"
  fi
else
  LOG "✗ demo_2_debate_execution.sh not found"
  exit 1
fi

echo ""
read -p "Press Enter to continue to Demo 3..." < /dev/tty
echo ""

# Demo 3: Reasoning & Logs
DEMO_SECTION "DEMO 3/3: Reasoning Process & Event Analysis"

LOG "[$(date '+%H:%M:%S')] Analyzing debate reasoning..."

if [ -f "$SCRIPT_DIR/demo_3_reasoning_logs.sh" ]; then
  if [ -n "$RUN_ID" ]; then
    # Use captured run_id
    export RUN_ID="$RUN_ID"
    export API_URL="http://localhost:8000/api"
    bash "$SCRIPT_DIR/demo_3_reasoning_logs.sh" "$RUN_ID" 2>&1 | tee -a "$LOG_FILE"
  elif [ -n "$1" ]; then
    # Use provided run_id
    bash "$SCRIPT_DIR/demo_3_reasoning_logs.sh" "$1" 2>&1 | tee -a "$LOG_FILE"
  else
    # Show usage
    bash "$SCRIPT_DIR/demo_3_reasoning_logs.sh" 2>&1 | tee -a "$LOG_FILE"
    echo ""
    echo "  To analyze the debate from Demo 2, provide the Run ID:"
    echo "  ./demo_all.sh <run_id>"
  fi
else
  LOG "✗ demo_3_reasoning_logs.sh not found"
  exit 1
fi

# Summary
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  ✅ DEMO COMPLETE                                             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

LOG ""
LOG "=== Demo Completed Successfully ==="
LOG "Ended: $(date)"
LOG "Log saved to: $LOG_FILE"

echo "📋 Full demo log saved to: $LOG_FILE"
echo ""
echo "📌 Key Commands:"
echo "   • View logs:     tail -f $LOG_FILE"
echo "   • Backend logs:  docker logs -f q-consensus-orchestrator"
echo "   • API docs:      http://localhost:8000/docs"
echo "   • Frontend:      http://localhost:8081"
echo ""

exit 0
