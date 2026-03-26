from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from .contract_anchor import ContractAnchoringClient
from .debate_policy import build_agent_prompts, build_cross_critique_prompt, build_self_revision_prompt
from .events import Event, JsonlEventStore, compute_run_commitment
from .llm_client import LlamaCppClient
from .quantum import (
    classical_random_bits,
    classical_schedule_scores,
    classical_weights_from_angles,
    quantum_random_bits,
    quantum_schedule_scores,
    quantum_weights_from_angles,
)
from .quantum_executor import QuantumExecutor
from .types import DebateConfig, DebateMessage, DebateResult


class DebateOrchestrator:
    def __init__(
        self,
        *,
        event_store: JsonlEventStore,
        llm: LlamaCppClient,
        quantum_executor: QuantumExecutor,
        contract_anchorer: Optional[ContractAnchoringClient] = None,
        anchor_contract_address: Optional[str] = None,
    ):
        self.event_store = event_store
        self.llm = llm
        self.quantum_executor = quantum_executor
        self.contract_anchorer = contract_anchorer
        self.anchor_contract_address = anchor_contract_address

    def _persist_event(self, *, run_id: str, event_type: str, payload: dict, prev_hash: Optional[str]) -> str:
        ev = Event.create(run_id=run_id, event_type=event_type, payload=payload, prev_event_hash=prev_hash)
        self.event_store.append(ev)
        return ev.event_hash

    @staticmethod
    def _build_order_from_scores(scores: List[float], n_agents: int) -> List[int]:
        return sorted(range(n_agents), key=lambda i: scores[i], reverse=True)

    @staticmethod
    def _pick_final_by_weights(agent_ids: List[str], answers: Dict[str, str], weights: List[float]) -> str:
        scored: List[tuple[float, str]] = []
        for i, aid in enumerate(agent_ids):
            w = weights[i] if i < len(weights) else 1.0
            content = answers.get(aid, "")
            scored.append((w * len(content), content))
        scored.sort(key=lambda t: t[0], reverse=True)
        return scored[0][1] if scored else ""

    def run(self, *, user_query: str, config: DebateConfig, run_id: Optional[str] = None) -> DebateResult:
        run_id = run_id or str(uuid.uuid4())

        prev_hash = self.event_store.get_tail_hash(run_id)
        prev_hash = self._persist_event(
            run_id=run_id,
            event_type="input_received",
            payload={"query": user_query},
            prev_hash=prev_hash,
        )

        seed = self.quantum_executor.current_seed
        n_agents = len(config.agents)
        agent_ids = [a.agent_id for a in config.agents]

        q_random = quantum_random_bits(n_bits=n_agents, executor=self.quantum_executor, seed=seed)
        c_random = classical_random_bits(n_bits=n_agents, seed=seed)
        quantum_order = sorted(range(n_agents), key=lambda i: q_random.bits[i])
        classical_order = sorted(range(n_agents), key=lambda i: c_random[i])
        selected_policy_random = "quantum" if config.quantum.use_quantum_randomness else "classical"
        selected_order = quantum_order if selected_policy_random == "quantum" else classical_order

        prev_hash = self._persist_event(
            run_id=run_id,
            event_type="quantum_randomness",
            payload={
                "seed_used": seed,
                "quantum_bits": q_random.bits,
                "classical_bits": c_random,
                "quantum_order": quantum_order,
                "classical_order": classical_order,
                "selected_order": selected_order,
                "selected_policy": selected_policy_random,
            },
            prev_hash=prev_hash,
        )

        q_sched = quantum_schedule_scores(n_agents=n_agents, executor=self.quantum_executor, shots=config.quantum.shots_scheduling, seed=seed)
        c_sched = classical_schedule_scores(n_agents=n_agents, seed=seed)
        selected_policy_sched = "quantum" if config.quantum.use_quantum_scheduling else "classical"
        selected_sched = q_sched if selected_policy_sched == "quantum" else c_sched
        scheduled_order = self._build_order_from_scores(selected_sched, n_agents)

        prev_hash = self._persist_event(
            run_id=run_id,
            event_type="quantum_scheduling",
            payload={
                "seed_used": seed,
                "quantum_scores": q_sched,
                "classical_scores": c_sched,
                "selected_scores": selected_sched,
                "selected_order": scheduled_order,
                "selected_policy": selected_policy_sched,
            },
            prev_hash=prev_hash,
        )

        messages: List[DebateMessage] = []
        initial_answers: Dict[str, str] = {}
        critiques: Dict[str, str] = {}
        revised_answers: Dict[str, str] = {}

        # Round 0: initial answers
        agent_prompts = build_agent_prompts(user_query=user_query, agents=config.agents)

        for idx in selected_order:
            agent = config.agents[idx]
            prompt_msgs = agent_prompts[agent.agent_id]

            prev_hash = self._persist_event(
                run_id=run_id,
                event_type="agent_prompted",
                payload={
                    "agent_id": agent.agent_id,
                    "display_name": agent.display_name,
                    "round_idx": 0,
                    "messages": prompt_msgs,
                },
                prev_hash=prev_hash,
            )

            content = self.llm.chat(messages=prompt_msgs)
            initial_answers[agent.agent_id] = content

            msg = DebateMessage(run_id=run_id, agent_id=agent.agent_id, role="assistant", content=content, round_idx=0)
            messages.append(msg)

            prev_hash = self._persist_event(
                run_id=run_id,
                event_type="agent_responded",
                payload={
                    "agent_id": agent.agent_id,
                    "display_name": agent.display_name,
                    "content": content,
                    "round_idx": 0,
                },
                prev_hash=prev_hash,
            )

        if config.max_rounds >= 2:
            for idx in scheduled_order:
                agent = config.agents[idx]
                own_answer = initial_answers.get(agent.agent_id, "")
                peer_answers = {aid: ans for aid, ans in initial_answers.items() if aid != agent.agent_id}
                prompt_msgs = build_cross_critique_prompt(
                    user_query=user_query,
                    agent=agent,
                    own_answer=own_answer,
                    peer_answers=peer_answers,
                )

                prev_hash = self._persist_event(
                    run_id=run_id,
                    event_type="agent_prompted",
                    payload={
                        "agent_id": agent.agent_id,
                        "display_name": agent.display_name,
                        "round_idx": 1,
                        "messages": prompt_msgs,
                    },
                    prev_hash=prev_hash,
                )

                content = self.llm.chat(messages=prompt_msgs)
                critiques[agent.agent_id] = content
                messages.append(DebateMessage(run_id=run_id, agent_id=agent.agent_id, role="assistant", content=content, round_idx=1))

                prev_hash = self._persist_event(
                    run_id=run_id,
                    event_type="agent_responded",
                    payload={
                        "agent_id": agent.agent_id,
                        "display_name": agent.display_name,
                        "content": content,
                        "round_idx": 1,
                    },
                    prev_hash=prev_hash,
                )

        if config.max_rounds >= 3:
            for idx in scheduled_order:
                agent = config.agents[idx]
                own_answer = initial_answers.get(agent.agent_id, "")
                critiques_from_peers = {aid: txt for aid, txt in critiques.items() if aid != agent.agent_id}
                prompt_msgs = build_self_revision_prompt(
                    user_query=user_query,
                    agent=agent,
                    own_answer=own_answer,
                    critiques_from_peers=critiques_from_peers,
                )

                prev_hash = self._persist_event(
                    run_id=run_id,
                    event_type="agent_prompted",
                    payload={
                        "agent_id": agent.agent_id,
                        "display_name": agent.display_name,
                        "round_idx": 2,
                        "messages": prompt_msgs,
                    },
                    prev_hash=prev_hash,
                )

                content = self.llm.chat(messages=prompt_msgs)
                revised_answers[agent.agent_id] = content
                messages.append(DebateMessage(run_id=run_id, agent_id=agent.agent_id, role="assistant", content=content, round_idx=2))

                prev_hash = self._persist_event(
                    run_id=run_id,
                    event_type="agent_responded",
                    payload={
                        "agent_id": agent.agent_id,
                        "display_name": agent.display_name,
                        "content": content,
                        "round_idx": 2,
                    },
                    prev_hash=prev_hash,
                )

        angles = [0.3 + (i * 0.7) for i in range(n_agents)]
        quantum_weights = quantum_weights_from_angles(
            angles=angles,
            executor=self.quantum_executor,
            shots=config.quantum.shots_weights,
            seed=seed,
        )
        classical_weights = classical_weights_from_angles(angles=angles)
        selected_policy_weights = "quantum" if config.quantum.use_quantum_weights else "classical"
        selected_weights = quantum_weights if selected_policy_weights == "quantum" else classical_weights

        prev_hash = self._persist_event(
            run_id=run_id,
            event_type="consensus_weights",
            payload={
                "angles": angles,
                "quantum_weights": quantum_weights,
                "classical_weights": classical_weights,
                "selected_weights": selected_weights,
                "selected_policy": selected_policy_weights,
            },
            prev_hash=prev_hash,
        )

        candidate_answers = revised_answers if revised_answers else initial_answers
        quantum_baseline_answer = self._pick_final_by_weights(agent_ids, candidate_answers, quantum_weights)
        classical_baseline_answer = self._pick_final_by_weights(agent_ids, candidate_answers, classical_weights)
        final_answer = quantum_baseline_answer if selected_policy_weights == "quantum" else classical_baseline_answer

        prev_hash = self._persist_event(
            run_id=run_id,
            event_type="final_answer",
            payload={
                "final_answer": final_answer,
                "quantum_baseline_answer": quantum_baseline_answer,
                "classical_baseline_answer": classical_baseline_answer,
                "selected_policy": selected_policy_weights,
            },
            prev_hash=prev_hash,
        )

        event_hashes = [e.event_hash for e in self.event_store.iter_events(run_id)]
        commitment = compute_run_commitment(event_hashes)

        anchor_tx_hash: Optional[str] = None
        anchor_error: Optional[str] = None
        if self.contract_anchorer is not None and self.anchor_contract_address:
            try:
                anchor_tx_hash = self.contract_anchorer.anchor_commitment(
                    run_id=run_id,
                    commitment=commitment,
                    contract_address=self.anchor_contract_address,
                )
            except Exception as exc:  # pragma: no cover - defensive path
                anchor_error = str(exc)

        prev_hash = self.event_store.get_tail_hash(run_id)
        prev_hash = self._persist_event(
            run_id=run_id,
            event_type="run_committed",
            payload={
                "commitment": commitment,
                "anchor_tx_hash": anchor_tx_hash,
                "anchor_contract_address": self.anchor_contract_address,
                "anchor_error": anchor_error,
            },
            prev_hash=prev_hash,
        )

        return DebateResult(
            run_id=run_id,
            final_answer=final_answer,
            messages=messages,
            commitment=commitment,
            anchor_tx_hash=anchor_tx_hash,
        )
