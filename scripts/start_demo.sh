#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo "Starting Docker services..."
docker compose up --build -d

echo "Waiting for services to become available..."
for i in {1..60}; do
  if curl -fsS http://localhost:8000/api/status >/dev/null 2>&1 && \
     curl -fsS http://localhost:8545 \
       -H 'Content-Type: application/json' \
       -d '{"jsonrpc":"2.0","method":"web3_clientVersion","params":[],"id":1}' >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [[ "$i" -eq 60 ]]; then
    echo "Timed out waiting for orchestrator/blockchain services"
    exit 1
  fi
done

contract_enabled="$(grep -E '^CONTRACT_ANCHOR_ENABLED=' .env | cut -d'=' -f2- | tr '[:upper:]' '[:lower:]' || true)"
contract_address="$(grep -E '^ANCHOR_CONTRACT_ADDRESS=' .env | cut -d'=' -f2- || true)"

if [[ "$contract_enabled" == "true" || "$contract_enabled" == "1" || "$contract_enabled" == "yes" ]]; then
  if [[ -z "$contract_address" ]]; then
    echo "Deploying anchor contract..."
    deploy_output="$(python3 scripts/deploy_contract.py)"
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
    else
      echo "Failed to parse contract address from deployment output"
      exit 1
    fi
  fi
fi

echo "Opening UI..."
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:8000" >/dev/null 2>&1 || true
fi

echo "Q-CONSENSUS is ready at http://localhost:8000"
echo "Use 'docker compose logs -f orchestrator' for live logs"
