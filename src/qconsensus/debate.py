from __future__ import annotations

import uuid
from typing import List, Optional

from .debate_policy import build_agent_prompts
from .eth_anchor import EthRunAnchoringClient
from .events import Event, JsonlEventStore, compute_run_commitment
from .llm_client import LlamaCppClient
from .quantum import quantum_random_bits, quantum_weights_from_angles
from .quantum_executor import QuantumExecutor
from .types import DebateConfig, DebateMessage, DebateResult


class DebateOrchestrator:
    def __init__(
        self,
        *,
        event_store: JsonlEventStore,
        llm: LlamaCppClient,
        quantum_executor: QuantumExecutor,
        eth_anchorer: Optional[EthRunAnchoringClient] = None,
    ):
        self.event_store = event_store
        self.llm = llm
        self.quantum_executor = quantum_executor
        self.eth_anchorer = eth_anchorer

    def run(self, *, user_query: str, config: DebateConfig) -> DebateResult:
        run_id = str(uuid.uuid4())

        prev_hash = self.event_store.get_tail_hash(run_id)
        ev = Event.create(run_id=run_id, event_type="input_received", payload={"query": user_query}, prev_event_hash=prev_hash)
        self.event_store.append(ev)
        prev_hash = ev.event_hash

        # Quantum randomness example: decide speaking order
        qr = quantum_random_bits(n_bits=len(config.agents), executor=self.quantum_executor, seed=self.quantum_executor.current_seed)
        order = sorted(range(len(config.agents)), key=lambda i: qr.bits[i])
        ev = Event.create(
            run_id=run_id,
            event_type="quantum_randomness",
            payload={"bits": qr.bits, "seed_used": qr.seed_used, "order": order},
            prev_event_hash=prev_hash,
        )
        self.event_store.append(ev)
        prev_hash = ev.event_hash

        messages: List[DebateMessage] = []

        # Round 0: initial answers
        agent_prompts = build_agent_prompts(user_query=user_query, agents=config.agents)

        for idx in order:
            agent = config.agents[idx]
            prompt_msgs = agent_prompts[agent.agent_id]

            ev = Event.create(
                run_id=run_id,
                event_type="agent_prompted",
                payload={"agent_id": agent.agent_id, "display_name": agent.display_name, "messages": prompt_msgs},
                prev_event_hash=prev_hash,
            )
            self.event_store.append(ev)
            prev_hash = ev.event_hash

            content = self.llm.chat(messages=prompt_msgs)

            msg = DebateMessage(run_id=run_id, agent_id=agent.agent_id, role="assistant", content=content, round_idx=0)
            messages.append(msg)

            ev = Event.create(
                run_id=run_id,
                event_type="agent_responded",
                payload={"agent_id": agent.agent_id, "display_name": agent.display_name, "content": content, "round_idx": 0},
                prev_event_hash=prev_hash,
            )
            self.event_store.append(ev)
            prev_hash = ev.event_hash

        # MVP consensus (placeholder): quantum-derived weights
        angles = [0.3, 1.2, 2.4][: len(config.agents)]
        weights = quantum_weights_from_angles(angles=angles, executor=self.quantum_executor, shots=256)
        ev = Event.create(
            run_id=run_id,
            event_type="quantum_weights",
            payload={"angles": angles, "weights": weights},
            prev_event_hash=prev_hash,
        )
        self.event_store.append(ev)
        prev_hash = ev.event_hash

        scored = []
        for i, msg in enumerate([m for m in messages if m.round_idx == 0]):
            w = weights[i] if i < len(weights) else 1.0
            scored.append((w * len(msg.content), msg.content))
        scored.sort(key=lambda t: t[0], reverse=True)
        final_answer = scored[0][1] if scored else ""

        ev = Event.create(
            run_id=run_id,
            event_type="final_answer",
            payload={"final_answer": final_answer},
            prev_event_hash=prev_hash,
        )
        self.event_store.append(ev)

        event_hashes = [e.event_hash for e in self.event_store.iter_events(run_id)]
        commitment = compute_run_commitment(event_hashes)

        anchor_tx_hash: Optional[str] = None
        if self.eth_anchorer is not None:
            anchor_tx_hash = self.eth_anchorer.anchor_run(run_id=run_id, commitment=commitment)

        prev_hash = self.event_store.get_tail_hash(run_id)
        ev = Event.create(
            run_id=run_id,
            event_type="run_committed",
            payload={"commitment": commitment, "anchor_tx_hash": anchor_tx_hash},
            prev_event_hash=prev_hash,
        )
        self.event_store.append(ev)

        return DebateResult(
            run_id=run_id,
            final_answer=final_answer,
            messages=messages,
            commitment=commitment,
            anchor_tx_hash=anchor_tx_hash,
        )
