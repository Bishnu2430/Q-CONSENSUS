# Q-CONSENSUS System Specification Document (SSD)

**Version**: 1.0 (LLM Debate Prototype Draft)

This document specifies the current direction of Q-CONSENSUS: a **multi-agent LLM debate system** with **end-to-end observability** anchored to a **real blockchain network**, while integrating **quantum computation primitives (via Qiskit)** into the orchestration and consensus process.

> Note on “all computing on quantum”
>
> With today’s practical constraints, **LLM inference itself will run on classical compute (CPU)**. The research goal is to maximize quantum computation where it is technically meaningful and measurable (randomness, aggregation/weighting, routing/optimization), and to report results honestly.

---

## 1. Objectives

### 1.1 Primary Objective

Given a user query (optionally with files/images), run a structured debate among N agents with distinct personas/roles, producing:

- A final answer
- A debate transcript (chat-style)
- Per-agent self-critique and cross-critique
- A deterministic, replayable execution trace
- Tamper-evident auditability using a blockchain network

### 1.2 Research Objective

Quantify the **impact of quantum-driven coordination** on:

- Consensus stability/reproducibility
- Quality proxies (consistency checks, agreement rate, verification success)
- Cost/latency trade-offs (CPU time, token throughput, quantum simulation cost)

---

## 2. System Overview

### 2.1 High-Level Components

1. **LLM Inference Service (CPU-only, Docker)**
   - Hosts a small model (3–4B parameter class) for agent responses.

2. **Orchestrator API (Python)**
   - Creates agents (persona + constraints)
   - Runs debate protocol
   - Calls quantum routines for randomness/aggregation/optimization
   - Emits structured events to storage + blockchain anchoring

3. **Quantum Services (Qiskit)**
   - (A) Quantum randomness/measurement for stochastic policy (sampling, tie-break)
   - (B) Quantum circuit(s) for aggregation/consensus weighting
   - (C) Quantum optimization heuristic for agent ordering / prompt routing

4. **Observability Store (Off-chain)**
   - Stores full event payloads (inputs/outputs/rationale summaries/metrics).

5. **Blockchain Network (On-chain)**
   - Anchors run commitments (hashes / Merkle roots) for tamper evidence.

6. **Minimal Web UI (Single page)**
   - Input
   - System status
   - Debate transcript
   - Reasoning/validation view

---

## 3. Agent Model

An agent is a configuration bundle:

- persona (system prompt)
- thinking style (skeptic/verifier/proposer)
- policy (turn-taking, length, evidence requirements)

Agents must be **meaningfully different** so that disagreement is likely, and differences must be deterministic from config (replayable).

---

## 4. Debate Protocol (MVP)

1. Input ingestion → create `run_id`
2. Agent initial answers
3. Cross-critique round
4. Self-revision round
5. Consensus (classical baseline + quantum-assisted variants)
6. Final response + export

---

## 5. Quantum Integration

### 5.1 (A) Quantum Randomness

Used for tie-breaking, agent order selection, and policy decisions.

### 5.2 (B) Quantum Aggregation / Weighting

Used to produce weights/thresholds for vote weighting and stability targets.

### 5.3 (C) Quantum Optimization

Used for routing/scheduling decisions under compute budget constraints.

### 5.4 Baselines

Every quantum-assisted decision must have a logged classical baseline.

---

## 6. Observability & Data Model

### 6.1 Event Schema

Every action emits an append-only event:

- `event_id`, `run_id`, `timestamp`
- `event_type`
- `payload` (full transparency)
- `hash` of canonical serialized payload

Reasoning policy: log prompts/outputs, but agents should emit **structured rationale summaries** rather than hidden chain-of-thought.

### 6.2 Off-chain vs On-chain Storage

- Off-chain: store full payloads + artifacts
- On-chain: store immutable commitments

---

## 7. Blockchain Network

Minimum requirements:

- Real network (local Docker network acceptable)
- Anchors run commitments
- Verifier tooling exists

Target prototype network:

- Private Ethereum PoA (geth clique)

---

## 8. Minimal Web UI

Single page with 4 panes:

1. Input (text + optional files/images)
2. System status (CPU/mem)
3. Debate transcript
4. Reasoning/validation

---

**Next**: See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) and [docs/TODO.md](docs/TODO.md).
