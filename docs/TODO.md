# Q-CONSENSUS — TODO (Detailed Checklist)

This is the execution checklist for the current prototype.

Status legend: `[ ]` not started, `[~]` in progress, `[x]` done.

---

## 0) Repo + runtime

- [x] Develop/run in Ubuntu (dual-boot) or WSL2 Ubuntu
- [x] Install Docker Engine + Compose
- [x] Choose model weights location (mounted volume)
- [x] Create `.env` and `.env.example` strategy

---

## 1) Orchestrator + debate MVP

- [~] FastAPI app exists
- [x] Add SSE live event stream endpoint
- [x] Add cross-critique round
- [x] Add self-revision round
- [x] Add deterministic consensus + logged baseline comparisons

---

## 2) Observability

- [x] Canonical hashing + event store
- [x] Add artifact store + file/image uploads
- [x] Add replay tool

---

## 3) Quantum hooks (A/B/C)

- [x] A) quantum randomness scaffolded
- [x] B) quantum weights scaffolded
- [x] C) quantum scheduling/routing primitive
- [x] Add classical baselines for each decision and log both

---

## 4) Blockchain network (geth clique)

- [x] Docker compose: blockchain container (geth clique)
- [x] Dev account creation + prefund
- [x] Anchoring MVP (tx data) + preferred contract-based anchoring
- [x] Verifier tool checks chain + on-chain anchor

---

## 5) Full docker-compose stack

- [x] `llm` service (llama.cpp)
- [x] `orchestrator` service
- [x] `.env.example`
- [x] Runbook doc

---

## 6) Demo readiness

- [x] One-command startup
- [x] UI shows input/status/debate/reasoning
- [x] End-to-end run is anchored + verifiable
