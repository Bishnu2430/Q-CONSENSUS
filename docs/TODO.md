# Q-CONSENSUS — TODO (Detailed Checklist)

This is the execution checklist for the current prototype.

Status legend: `[ ]` not started, `[~]` in progress, `[x]` done.

---

## 0) Repo + runtime

- [ ] Develop/run in Ubuntu (dual-boot) or WSL2 Ubuntu
- [ ] Install Docker Engine + Compose
- [ ] Choose model weights location (mounted volume)
- [ ] Create `.env` and `.env.example` strategy

---

## 1) Orchestrator + debate MVP

- [~] FastAPI app exists
- [ ] Add SSE live event stream endpoint
- [ ] Add cross-critique round
- [ ] Add self-revision round
- [ ] Add deterministic consensus + logged baseline comparisons

---

## 2) Observability

- [x] Canonical hashing + event store
- [ ] Add artifact store + file/image uploads
- [ ] Add replay tool

---

## 3) Quantum hooks (A/B/C)

- [~] A) quantum randomness scaffolded
- [~] B) quantum weights scaffolded
- [ ] C) quantum scheduling/routing primitive
- [ ] Add classical baselines for each decision and log both

---

## 4) Blockchain network (geth clique)

- [ ] Docker compose: geth clique
- [ ] Dev account creation + prefund
- [ ] Anchoring MVP (tx data) + preferred contract-based anchoring
- [ ] Verifier tool checks chain + on-chain anchor

---

## 5) Full docker-compose stack

- [ ] `llm` service (llama.cpp)
- [ ] `orchestrator` service
- [ ] `.env.example`
- [ ] Runbook doc

---

## 6) Demo readiness

- [ ] One-command startup
- [ ] UI shows input/status/debate/reasoning
- [ ] End-to-end run is anchored + verifiable
