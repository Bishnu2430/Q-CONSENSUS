# Q-CONSENSUS — Handoff Context (Resume on Ubuntu)

Date: 2026-03-25

This file is a single source of truth to resume work after switching machines/OS.

---

## Latest verified state (2026-03-25)

- Docker stack is up and healthy:
  - API: `http://localhost:8000`
  - llama.cpp: `http://localhost:8080`
  - geth RPC: `http://localhost:8545`
- Real inference verified (`MOCK_LLM=false`) using local GGUF model:
  - `models/Qwen2.5-3B-Instruct-Q4_K_M.gguf`
- Contract anchoring configured in `.env`:
  - `CONTRACT_ANCHOR_ENABLED=true`
  - `ANCHOR_CONTRACT_ADDRESS=0x5FC8d32690cc91D4c39d9d3abcBD16989F875707`
- End-to-end anchor verification completed for run:
  - `run_id=b3b7c625-4cde-43a2-8106-6eb5a9e582ce`
  - commitment matched on-chain after tx confirmation
- Persistence is enabled via volumes/binds:
  - `./data:/app/data`
  - `./models:/models`
  - `pgdata` (postgres)
  - `gethdata` (chain state)

---

## What we decided

- Target OS/workflow: **Ubuntu** (dual boot). (WSL2 Ubuntu also acceptable.)
- LLM runtime: **llama.cpp server** (CPU-only), OpenAI-compatible endpoint.
- Blockchain network: **Private Ethereum PoA (geth clique)** in Docker.
- Observability stance: **maximum transparency** for research; log prompts/outputs and operational metrics.
- Reasoning policy: store **structured rationale summaries** (not hidden chain-of-thought).
- Quantum role (v2): integrate Qiskit-based primitives into orchestration:
  - (A) quantum randomness
  - (B) quantum aggregation/weighting
  - (C) quantum scheduling/routing optimization
  - Always include classical baselines for fair comparison.

---

## Current repo state (important)

### Main (renamed from v2)

- The repo has been migrated to keep the v2 prototype as the **main** codebase.
- Main docs:
  - `docs/SYSTEM_SPECIFICATION_DOCUMENT.md`
  - `docs/IMPLEMENTATION_PLAN.md`
  - `docs/TODO.md`
  - `docs/HANDOFF_CONTEXT.md`

### Main code scaffold

- Package: `src/qconsensus/` (import path: `src.qconsensus`)
  - `events.py`: canonical JSON hashing, event hash chain, JSONL store, run commitment
  - `web.py`: FastAPI app + minimal single-page UI (4 panes)
  - `llm_client.py`: llama.cpp OpenAI-compatible client
  - `debate.py`: DebateOrchestrator (MVP: initial agent answers → simple selection → commitment → optional Ethereum anchor)
  - `debate_policy.py`: agent prompt builder with rationale summary rules
  - `quantum.py`: quantum randomness bits + quantum weight primitive
  - `quantum_executor.py`: Qiskit Aer execution layer
  - `eth_anchor.py`: MVP anchoring client (tx-to-self with `data` payload)

### Tests

- Existing tests for v1 agent layer pass.
- `pytest` run inside conda env succeeded: **17 passed**.

---

## Environment notes

### Conda env

- You requested using conda env: `qc_env`.
- VS Code interpreter points to: `C:\Users\karbi\miniconda3\envs\qc_env\python.exe` (on Windows).

### Important: Terminal vs interpreter

- When using a terminal, ensure commands run inside `qc_env`.

---

## How to run v2 locally (without Docker yet)

1. Start llama.cpp server (not yet added to repo; will be Dockerized in next step)
2. Run orchestrator:

- `uvicorn src.qconsensus.web:app --reload --port 8000`

3. Open: `http://localhost:8000/`

Ethereum anchoring is optional via env vars:

- `ETH_ANCHOR_ENABLED=true`
- `ETH_RPC_URL=http://...`
- `ETH_CHAIN_ID=...`
- `ETH_FROM_ADDRESS=0x...`
- `ETH_PRIVATE_KEY=...`

Event storage:

- `EVENT_STORE_DIR` env var; defaults to `data/events`

---

## Next work items (the immediate next step)

- Add Docker templates:
  - `docker-compose.yml` for llama.cpp + orchestrator + geth clique
  - Orchestrator `Dockerfile`
  - `.env.example`
- Improve debate protocol:
  - cross-critique + self-revision rounds
  - SSE streaming to UI
- Replace MVP anchoring with a simple anchor contract (optional but preferred)

---

## Files created/edited in this session

Docs:

- `docs/SYSTEM_SPECIFICATION_DOCUMENT.md` (updated to main v2-only SSD)
- `docs/IMPLEMENTATION_PLAN.md` (new)
- `docs/TODO.md` (new)
- `docs/HANDOFF_CONTEXT.md` (new)

Code:

- `src/qconsensus/*` (new)

Dependencies:

- `requirements.txt` (added FastAPI/uvicorn/psutil/web3/etc)

---

## Cleanup

- Deletion scope was confirmed: remove the old v1 stubs/tests/notebooks/experiments and keep the v2 prototype as main.
