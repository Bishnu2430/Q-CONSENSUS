# Q-CONSENSUS Runbook (Ubuntu)

## 1. Local uv setup

1. Create environment and install dependencies:

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

2. Start API locally:

```bash
source .venv/bin/activate
uvicorn src.qconsensus.web:app --reload --port 8000
```

3. Open UI:

- http://localhost:8000/

## 2. Docker stack setup

### One-command startup (recommended)

```bash
./scripts/start_demo.sh
```

What it does:

- Starts docker services (`orchestrator`, `llama`, `blockchain`, `postgres`)
- Waits for API and blockchain readiness
- If `CONTRACT_ANCHOR_ENABLED=true` and `ANCHOR_CONTRACT_ADDRESS` is empty, deploys anchor contract and writes address to `.env`
- Recreates orchestrator service to pick up the new contract address
- Opens the interface at `http://localhost:8000`

Manual steps (optional) are below.

1. Copy environment file:

```bash
cp .env.example .env
```

2. Put a GGUF model in `models/` and ensure `.env` has `LLAMA_MODEL_FILE` set.

Recommended starter model:

- `Qwen2.5-3B-Instruct-Q4_K_M.gguf`

3. Start stack:

```bash
docker compose up --build -d
```

4. Confirm services are healthy:

```bash
docker compose ps
curl -s http://localhost:8080/health
curl -s http://localhost:8000/api/status
```

5. Stop stack:

```bash
docker compose down
```

6. Rebuild from scratch:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

7. Services:

- Orchestrator API/UI: http://localhost:8000
- llama.cpp server: http://localhost:8080
- Blockchain RPC (Geth clique): http://localhost:8545
- Postgres: localhost:5432

8. Verify real LLM inference (non-mock):

```bash
curl -s http://localhost:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"Qwen2.5-3B-Instruct-Q4_K_M.gguf",
    "messages":[{"role":"user","content":"Reply with: ok"}],
    "max_tokens":8,
    "temperature":0
  }'
```

## 3. Agent spawning

Agent specs are read from `config/agents.yaml` (path configurable via `AGENTS_CONFIG_PATH`).

- Add/remove entries in `agents:` to scale agent count.
- Each entry requires:
  - `agent_id`
  - `display_name`
  - `system_prompt`

## 4. Debate protocol (implemented)

- Round 0: initial answers
- Round 1: cross-critique
- Round 2: self-revision
- Consensus: weighted scoring with quantum/classical baseline logging

## 5. Quantum layer (implemented)

- A) Quantum randomness for initial speaking order + classical baseline
- B) Quantum weighting for consensus + classical baseline
- C) Quantum scheduling scores for round ordering + classical baseline

All baseline/selection decisions are written as events.

## 6. Anchoring and data

- Event store: `data/events/*.jsonl`
- Artifact store: `data/artifacts/`
- On-chain anchoring uses contract settings (`CONTRACT_ANCHOR_ENABLED`, `ANCHOR_CONTRACT_ADDRESS`)
- RPC/key/chain parameters are read from `ETH_*` environment variables
- Current blockchain container uses private Geth clique PoA network (chain id 1337)

### Deploy/verify commitment contract

Use the helper script to deploy a compatible contract to local geth:

```bash
uv pip install --python .venv/bin/python py-solc-x
.venv/bin/python scripts/deploy_contract.py
```

Then set `.env`:

```dotenv
CONTRACT_ANCHOR_ENABLED=true
ANCHOR_CONTRACT_ADDRESS=<printed address>
```

### End-to-end contract anchor verification

1. Run debate:

```bash
curl -s -X POST http://localhost:8000/api/run \
  -H 'Content-Type: application/json' \
  -d '{"query":"status check"}'
```

2. Use returned `run_id` + `commitment` and check `/api/verify/{run_id}`.

3. Wait for tx receipt before verifying storage read.

### Persistence and Docker volumes

Current compose configuration persists data across container recreate/rebuild:

- `./data:/app/data` keeps events/artifacts on host
- `./models:/models` keeps GGUF models on host
- `pgdata` named volume keeps Postgres data
- `gethdata` named volume keeps chain state/account data

If you want a fresh blockchain genesis, remove only geth volume:

```bash
docker compose down
docker volume rm q-consensus_gethdata
docker compose up -d --build blockchain
```

## 7. API endpoints

- `POST /api/run` synchronous run
- `POST /api/run_async` async run + immediate run id
- `GET /api/stream/{run_id}` SSE event stream
- `GET /api/result/{run_id}` run status/result
- `GET /api/events/{run_id}` all persisted events
- `GET /api/status` host metrics
- `POST /api/replay/{run_id}` deterministic replay
- `GET /api/verify/{run_id}` chain verification
- `GET /api/metrics` aggregated metrics
- `GET /api/metrics/quantum-vs-classical` breakdown metrics
