# Q-CONSENSUS Implementation Plan

**Plan Version**: 1.0 (Draft)

Goal: deliver a **single-page demo** that runs a **multi-agent debate** on a user query, with **full observability** anchored to a **blockchain network**, and with **quantum routines integrated** into orchestration/consensus.

---

## Guiding Principles

- End-to-end first: ship a thin vertical slice before expanding.
- Reproducible: fixed seeds, deterministic configs, replay support.
- Honest baselines: every quantum feature gets a classical comparator.
- Blockchain for integrity (not bulk storage): store payloads off-chain; anchor hashes on-chain.

---

## Phase 1 — Vertical Slice (MVP demo)

Deliverables:

- Docker compose brings up:
  - LLM server (CPU)
  - Orchestrator API (Python)
  - Blockchain network (private PoA)
  - Web UI (single page)
- One debate run with 3 agents, 2 rounds, final consensus
- Full event log stored off-chain + anchored on-chain

Steps:

1. Define canonical event schema + hashing rules
2. Implement local event store (JSONL) + artifact storage
3. Implement blockchain anchoring (MVP tx data, then contract)
4. Implement orchestrator debate protocol
5. Implement minimal UI with live updates

---

## Phase 2 — Config & Scaling to N Agents

Deliverables:

- YAML config for agent personas, debate protocol, quantum toggles, baselines
- N-agent support
- Replay tool

---

## Phase 3 — Quantum Integration (Measurable)

- (A) Quantum randomness with reproducible seeds
- (B) Quantum aggregation/weighting strategies
- (C) Quantum scheduling/routing optimization
- Add metrics comparing quantum vs classical baselines

---

## Phase 4 — Observability Hardening

- System metrics collection in UI
- Integrity verifier tool
- Optional: OpenTelemetry

---

## Model & Inference (CPU-only, 3–4B)

Recommended inference stack:

- llama.cpp server with GGUF quantized weights

Candidate model shortlist:

- Qwen2.5 3B Instruct
- Phi-3.5-mini

---

Next: see `docs/TODO.md`.
