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

4. Stop stack:

```bash
docker compose down
```

5. Rebuild from scratch:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

6. Services:

- Orchestrator API/UI: http://localhost:8000
- llama.cpp server: http://localhost:8080
- Blockchain RPC (Geth clique): http://localhost:8545
- Postgres: localhost:5432

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
- On-chain anchoring via `ETH_*` environment variables
- Preferred anchoring mode uses contract settings (`CONTRACT_ANCHOR_ENABLED`, `ANCHOR_CONTRACT_ADDRESS`)
- Current blockchain container uses private Geth clique PoA network (chain id 1337)

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
