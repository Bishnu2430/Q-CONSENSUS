#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="python3"
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
fi

wait_for() {
  local name="$1"
  local max_attempts="$2"
  local sleep_seconds="$3"
  shift 3
  local cmd=("$@")

  for i in $(seq 1 "$max_attempts"); do
    if "${cmd[@]}" >/dev/null 2>&1; then
      echo "[ok] $name"
      return 0
    fi
    sleep "$sleep_seconds"
  done

  echo "[error] timed out waiting for $name"
  return 1
}

start_compose_with_retries() {
  local max_attempts=4
  local sleep_seconds=3
  local attempt=1
  local output

  while [[ "$attempt" -le "$max_attempts" ]]; do
    if output=$(COMPOSE_BAKE=false docker compose up --build -d 2>&1); then
      echo "$output"
      return 0
    fi

    echo "$output"

    if echo "$output" | grep -qiE 'registry-1\.docker\.io|server misbehaving|temporary failure in name resolution|lookup .*:53'; then
      echo "[warn] Docker registry DNS lookup failed (attempt $attempt/$max_attempts)."
      echo "[info] Retrying in ${sleep_seconds}s..."
      sleep "$sleep_seconds"
      sleep_seconds=$((sleep_seconds * 2))
      attempt=$((attempt + 1))
      continue
    fi

    echo "[error] docker compose failed for a non-retryable reason"
    return 1
  done

  echo "[error] docker compose failed after $max_attempts attempts due to registry/DNS resolution issues"
  echo "[hint] Check DNS settings for Docker daemon or retry when network resolution is stable"
  return 1
}

env_value() {
  local key="$1"
  grep -E "^${key}=" .env | head -n1 | cut -d'=' -f2-
}

if ! command -v docker >/dev/null 2>&1; then
  echo "[error] docker is not installed or not on PATH"
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "[error] docker daemon is not running"
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

model_file="$(env_value LLAMA_MODEL_FILE || true)"
if [[ -z "$model_file" ]]; then
  echo "[error] LLAMA_MODEL_FILE is missing in .env"
  exit 1
fi

if [[ ! -f "models/$model_file" ]]; then
  echo "[error] model file not found: models/$model_file"
  echo "Place your GGUF model in models/ and set LLAMA_MODEL_FILE in .env"
  exit 1
fi

echo "Starting Docker services..."
start_compose_with_retries

echo "Running health checks..."

wait_for "blockchain RPC" 90 2 \
  curl -fsS http://localhost:8545 \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","method":"web3_clientVersion","params":[],"id":1}'

wait_for "llama server" 120 2 \
  curl -fsS http://localhost:8080/health

wait_for "orchestrator API" 90 2 \
  curl -fsS http://localhost:8000/api/status

wait_for "frontend page" 90 2 \
  curl -fsS http://localhost:8000

contract_enabled="$(env_value CONTRACT_ANCHOR_ENABLED | tr '[:upper:]' '[:lower:]' || true)"
contract_address="$(env_value ANCHOR_CONTRACT_ADDRESS || true)"

if [[ "$contract_enabled" == "true" || "$contract_enabled" == "1" || "$contract_enabled" == "yes" ]]; then
  if [[ -z "$contract_address" ]]; then
    if [[ ! -x "$PYTHON_BIN" ]] && ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
      echo "[error] python is required to deploy anchor contract"
      exit 1
    fi

    if ! "$PYTHON_BIN" -c "import web3" >/dev/null 2>&1; then
      echo "[error] missing python dependency: web3"
      echo "Install it with: $PYTHON_BIN -m pip install web3"
      exit 1
    fi

    if ! "$PYTHON_BIN" -c "import solcx" >/dev/null 2>&1; then
      echo "Installing missing dependency: py-solc-x"
      "$PYTHON_BIN" -m pip install py-solc-x
    fi

    echo "Deploying anchor contract..."
    deploy_output="$("$PYTHON_BIN" scripts/deploy_contract.py)"
    echo "$deploy_output"
    addr="$(echo "$deploy_output" | awk -F= '/^ANCHOR_CONTRACT_ADDRESS=/{print $2}' | tail -n1)"
    if [[ -n "$addr" ]]; then
      if grep -q '^ANCHOR_CONTRACT_ADDRESS=' .env; then
        sed -i "s|^ANCHOR_CONTRACT_ADDRESS=.*|ANCHOR_CONTRACT_ADDRESS=$addr|" .env
      else
        echo "ANCHOR_CONTRACT_ADDRESS=$addr" >> .env
      fi
      echo "Updated .env with ANCHOR_CONTRACT_ADDRESS=$addr"

      echo "Restarting orchestrator to load contract address..."
      docker compose up -d --force-recreate orchestrator

      wait_for "orchestrator API (post-restart)" 90 2 \
        curl -fsS http://localhost:8000/api/status
    else
      echo "Failed to parse contract address from deployment output"
      exit 1
    fi
  fi
fi

echo "Service summary:"
docker compose ps

echo "Opening UI..."
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:8000" >/dev/null 2>&1 || true
fi

echo "Q-CONSENSUS is ready at http://localhost:8000"
echo "Use 'docker compose logs -f orchestrator' for live logs"
