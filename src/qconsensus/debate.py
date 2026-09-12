from __future__ import annotations

import logging
import time
import uuid
from typing import Dict, List, Optional

import numpy as np

from .contract_anchor import ContractAnchoringClient
from .debate_policy import build_agent_prompts, build_cross_critique_prompt, build_self_revision_prompt
from .events import Event, JsonlEventStore, compute_run_commitment
from .llm_client import LlamaCppClient
from .quantum_executor import QuantumExecutor
from .quantum_kernel import average_pairwise_similarity, pairwise_similarity_matrix
from .quantum_ordering import diversity_order
from .quantum_qaoa import build_maxcut_qubo, classical_solve_qubo, solve_qubo_qaoa
from .types import DebateConfig, DebateMessage, DebateResult
from .web_context import fetch_web_context

logger = logging.getLogger(__name__)


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
    def _pick_final_by_weights(agent_ids: List[str], answers: Dict[str, str], weights: List[float]) -> str:
        scored: List[tuple[float, str]] = []
        for i, aid in enumerate(agent_ids):
            w = weights[i] if i < len(weights) else 1.0
            content = answers.get(aid, "")
            scored.append((w * len(content), content))
        scored.sort(key=lambda t: t[0], reverse=True)
        return scored[0][1] if scored else ""

    @staticmethod
    def _weights_from_partition(partition: List[int], similarity: np.ndarray) -> List[float]:
        """Turn a Max-Cut bipartition into per-agent weights.

        Agents in the larger ("consensus") partition get full base weight;
        agents in the smaller ("dissenting") partition are down-weighted.
        Within each group, weight is further scaled by how similar an agent
        is to its own group -- an agent that only loosely matches its
        cluster still counts less than one that matches it closely.
        """
        n = len(partition)
        if n == 0:
            return []
        if n == 1:
            return [1.0]

        group_counts = {0: partition.count(0), 1: partition.count(1)}
        majority_label = 0 if group_counts[0] >= group_counts[1] else 1

        raw: List[float] = []
        for i in range(n):
            own_group = partition[i]
            peers = [j for j in range(n) if j != i and partition[j] == own_group]
            cohesion = float(np.mean([similarity[i, j] for j in peers])) if peers else 0.5
            base = 1.0 if own_group == majority_label else 0.4
            raw.append(base * (0.5 + 0.5 * cohesion))

        total = sum(raw)
        if total <= 0:
            return [1.0 / n] * n
        return [r / total for r in raw]

    def run(
        self,
        *,
        user_query: str,
        config: DebateConfig,
        run_id: Optional[str] = None,
        enable_web_context: bool = False,
        web_context_query: Optional[str] = None,
        web_context_max_items: int = 3,
    ) -> DebateResult:
        run_id = run_id or str(uuid.uuid4())

        prev_hash = self.event_store.get_tail_hash(run_id)
        prev_hash = self._persist_event(
            run_id=run_id,
            event_type="input_received",
            payload={"query": user_query},
            prev_hash=prev_hash,
        )

        effective_query = user_query
        if enable_web_context:
            prev_hash = self._persist_event(
                run_id=run_id,
                event_type="web_fetch_started",
                payload={"query": web_context_query or user_query},
                prev_hash=prev_hash,
            )
            
            web_start_time = time.time()
            lookup_query = (web_context_query or user_query).strip()
            context_items = fetch_web_context(lookup_query, max_items=web_context_max_items)
            web_duration_ms = int((time.time() - web_start_time) * 1000)
            
            if context_items:
                context_text = "\n".join(
                    [f"- {item.get('snippet', '')} (source: {item.get('url', '')})" for item in context_items]
                )
                effective_query = (
                    f"{user_query}\n\nExternal context (use as supportive evidence, validate internally):\n{context_text}"
                )

            prev_hash = self._persist_event(
                run_id=run_id,
                event_type="web_fetch_completed",
                payload={
                    "query": lookup_query,
                    "items_count": len(context_items),
                    "duration_ms": web_duration_ms,
                    "items": context_items,
                },
                prev_hash=prev_hash,
            )
            
            prev_hash = self._persist_event(
                run_id=run_id,
                event_type="web_context_enriched",
                payload={
                    "enabled": True,
                    "lookup_query": lookup_query,
                    "items_count": len(context_items),
                    "items": context_items,
                },
                prev_hash=prev_hash,
            )


        seed = self.quantum_executor.current_seed
        n_agents = len(config.agents)
        agent_ids = [a.agent_id for a in config.agents]

        # Round-0 speaking order: split agents into two mutually-dissimilar
        # clusters (by system-prompt content, the only thing available
        # before any answer exists) via a QAOA-solved Max-Cut, then
        # interleave the clusters. Adjacent speakers tend to represent
        # different perspectives -- a real, checkable ordering criterion
        # instead of a random bit.
        system_prompts = {a.agent_id: a.system_prompt for a in config.agents}
        order_result = diversity_order(
            agent_ids=agent_ids,
            texts=system_prompts,
            executor=self.quantum_executor,
            n_qubits=config.quantum.kernel_qubits,
            shots=config.quantum.shots_randomness if config.quantum.shots_randomness > 1 else 256,
            seed=seed,
        )
        selected_policy_random = "quantum" if config.quantum.use_quantum_randomness else "classical"
        selected_order = (
            order_result.quantum_order if selected_policy_random == "quantum" else order_result.classical_order
        )

        prev_hash = self._persist_event(
            run_id=run_id,
            event_type="quantum_randomness",
            payload={
                "seed_used": seed,
                "quantum_partition": order_result.quantum_partition,
                "classical_partition": order_result.classical_partition,
                "quantum_order": order_result.quantum_order,
                "classical_order": order_result.classical_order,
                "selected_order": selected_order,
                "selected_policy": selected_policy_random,
                "basis": "system_prompt_diversity",
            },
            prev_hash=prev_hash,
        )

        messages: List[DebateMessage] = []
        initial_answers: Dict[str, str] = {}
        critiques: Dict[str, str] = {}
        revised_answers: Dict[str, str] = {}

        # Round 0: initial answers
        agent_prompts = build_agent_prompts(user_query=effective_query, agents=config.agents)

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

            prev_hash = self._persist_event(
                run_id=run_id,
                event_type="llm_processing_started",
                payload={"agent_id": agent.agent_id, "round_idx": 0},
                prev_hash=prev_hash,
            )
            
            try:
                llm_start_time = time.time()
                content = self.llm.chat(messages=prompt_msgs)
                llm_duration_ms = int((time.time() - llm_start_time) * 1000)
                
                prev_hash = self._persist_event(
                    run_id=run_id,
                    event_type="llm_processing_completed",
                    payload={
                        "agent_id": agent.agent_id,
                        "round_idx": 0,
                        "duration_ms": llm_duration_ms,
                        "output_tokens": len(content.split()),
                    },
                    prev_hash=prev_hash,
                )
                
                initial_answers[agent.agent_id] = content
            except Exception as e:
                logger.error("[DEBATE] run_id=%s agent_id=%s round_idx=0 llm_error=%s", run_id, agent.agent_id, e)
                prev_hash = self._persist_event(
                    run_id=run_id,
                    event_type="llm_error",
                    payload={
                        "agent_id": agent.agent_id,
                        "error": str(e),
                        "round_idx": 0,
                    },
                    prev_hash=prev_hash,
                )
                raise

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


        # Critique/revision order: now that round 0 produced real answers,
        # base the scheduling order on *answer* diversity rather than the
        # system-prompt-only signal used for round 0 -- agents whose
        # answers landed in different clusters get interleaved so critique
        # naturally alternates between differing viewpoints.
        schedule_result = diversity_order(
            agent_ids=agent_ids,
            texts=initial_answers,
            executor=self.quantum_executor,
            n_qubits=config.quantum.kernel_qubits,
            shots=config.quantum.shots_scheduling,
            seed=seed,
        )
        selected_policy_sched = "quantum" if config.quantum.use_quantum_scheduling else "classical"
        scheduled_order = (
            schedule_result.quantum_order if selected_policy_sched == "quantum" else schedule_result.classical_order
        )

        prev_hash = self._persist_event(
            run_id=run_id,
            event_type="quantum_scheduling",
            payload={
                "seed_used": seed,
                "quantum_partition": schedule_result.quantum_partition,
                "classical_partition": schedule_result.classical_partition,
                "quantum_order": schedule_result.quantum_order,
                "classical_order": schedule_result.classical_order,
                "selected_order": scheduled_order,
                "selected_policy": selected_policy_sched,
                "basis": "initial_answer_diversity",
            },
            prev_hash=prev_hash,
        )

        effective_max_rounds = config.max_rounds
        if config.quantum.use_quantum_convergence and n_agents >= 2 and config.max_rounds >= 2:
            q_conv_matrix = pairwise_similarity_matrix(
                agent_ids=agent_ids,
                texts=initial_answers,
                kind="quantum",
                executor=self.quantum_executor,
                n_qubits=config.quantum.kernel_qubits,
                shots=config.quantum.shots_convergence,
                seed=seed,
            )
            c_conv_matrix = pairwise_similarity_matrix(
                agent_ids=agent_ids, texts=initial_answers, kind="classical"
            )
            q_avg_similarity = average_pairwise_similarity(q_conv_matrix)
            c_avg_similarity = average_pairwise_similarity(c_conv_matrix)
            avg_similarity = q_avg_similarity
            converged = avg_similarity >= config.quantum.convergence_similarity_threshold
            if converged:
                effective_max_rounds = 1

            prev_hash = self._persist_event(
                run_id=run_id,
                event_type="quantum_convergence_check",
                payload={
                    "seed_used": seed,
                    "quantum_avg_similarity": q_avg_similarity,
                    "classical_avg_similarity": c_avg_similarity,
                    "threshold": config.quantum.convergence_similarity_threshold,
                    "converged": converged,
                    "configured_max_rounds": config.max_rounds,
                    "effective_max_rounds": effective_max_rounds,
                },
                prev_hash=prev_hash,
            )

        if effective_max_rounds >= 2:
            for idx in scheduled_order:
                agent = config.agents[idx]
                own_answer = initial_answers.get(agent.agent_id, "")
                peer_answers = {aid: ans for aid, ans in initial_answers.items() if aid != agent.agent_id}
                prompt_msgs = build_cross_critique_prompt(
                    user_query=effective_query,
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

                prev_hash = self._persist_event(
                    run_id=run_id,
                    event_type="llm_processing_started",
                    payload={"agent_id": agent.agent_id, "round_idx": 1},
                    prev_hash=prev_hash,
                )
                
                try:
                    llm_start_time = time.time()
                    content = self.llm.chat(messages=prompt_msgs)
                    llm_duration_ms = int((time.time() - llm_start_time) * 1000)
                    
                    prev_hash = self._persist_event(
                        run_id=run_id,
                        event_type="llm_processing_completed",
                        payload={
                            "agent_id": agent.agent_id,
                            "round_idx": 1,
                            "duration_ms": llm_duration_ms,
                            "output_tokens": len(content.split()),
                        },
                        prev_hash=prev_hash,
                    )
                    
                    critiques[agent.agent_id] = content
                except Exception as e:
                    logger.error("[DEBATE] run_id=%s agent_id=%s round_idx=1 llm_error=%s", run_id, agent.agent_id, e)
                    prev_hash = self._persist_event(
                        run_id=run_id,
                        event_type="llm_error",
                        payload={
                            "agent_id": agent.agent_id,
                            "error": str(e),
                            "round_idx": 1,
                        },
                        prev_hash=prev_hash,
                    )
                    raise
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


        if effective_max_rounds >= 3:
            for idx in scheduled_order:
                agent = config.agents[idx]
                own_answer = initial_answers.get(agent.agent_id, "")
                critiques_from_peers = {aid: txt for aid, txt in critiques.items() if aid != agent.agent_id}
                prompt_msgs = build_self_revision_prompt(
                    user_query=effective_query,
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

                prev_hash = self._persist_event(
                    run_id=run_id,
                    event_type="llm_processing_started",
                    payload={"agent_id": agent.agent_id, "round_idx": 2},
                    prev_hash=prev_hash,
                )
                
                try:
                    llm_start_time = time.time()
                    content = self.llm.chat(messages=prompt_msgs)
                    llm_duration_ms = int((time.time() - llm_start_time) * 1000)
                    
                    prev_hash = self._persist_event(
                        run_id=run_id,
                        event_type="llm_processing_completed",
                        payload={
                            "agent_id": agent.agent_id,
                            "round_idx": 2,
                            "duration_ms": llm_duration_ms,
                            "output_tokens": len(content.split()),
                        },
                        prev_hash=prev_hash,
                    )
                    
                    revised_answers[agent.agent_id] = content
                except Exception as e:
                    logger.error("[DEBATE] run_id=%s agent_id=%s round_idx=2 llm_error=%s", run_id, agent.agent_id, e)
                    prev_hash = self._persist_event(
                        run_id=run_id,
                        event_type="llm_error",
                        payload={
                            "agent_id": agent.agent_id,
                            "error": str(e),
                            "round_idx": 2,
                        },
                        prev_hash=prev_hash,
                    )
                    raise
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


        prev_hash = self._persist_event(
            run_id=run_id,
            event_type="consensus_started",
            payload={
                "agent_count": n_agents,
                "round_count": effective_max_rounds,
                "configured_max_rounds": config.max_rounds,
                "use_quantum_weights": config.quantum.use_quantum_weights,
            },
            prev_hash=prev_hash,
        )

        consensus_start_time = time.time()

        candidate_answers = revised_answers if revised_answers else initial_answers

        # Consensus weighting: cluster agents by answer similarity via a
        # Max-Cut QUBO solved with QAOA (cutting apart dissimilar pairs
        # concentrates mutually-agreeing agents into the same partition).
        # The majority partition is the "consensus cluster" and gets full
        # weight; the minority partition is down-weighted as dissenting
        # outliers. This decides which agent's answer becomes the final
        # answer -- a real, checkable effect of the quantum computation,
        # not a random tiebreaker.
        if n_agents >= 2:
            q_similarity = pairwise_similarity_matrix(
                agent_ids=agent_ids,
                texts=candidate_answers,
                kind="quantum",
                executor=self.quantum_executor,
                n_qubits=config.quantum.kernel_qubits,
                shots=config.quantum.shots_weights,
                seed=seed,
            )
            c_similarity = pairwise_similarity_matrix(
                agent_ids=agent_ids, texts=candidate_answers, kind="classical"
            )

            q_dissimilarity = 1.0 - q_similarity
            np.fill_diagonal(q_dissimilarity, 0.0)
            q_qubo = build_maxcut_qubo(q_dissimilarity)
            q_qaoa_result = solve_qubo_qaoa(
                Q=q_qubo,
                executor=self.quantum_executor,
                p=1,
                shots=config.quantum.shots_weights,
                maxiter=20,
                seed=seed,
            )
            quantum_partition = q_qaoa_result.bitstring
            quantum_weights = self._weights_from_partition(quantum_partition, q_similarity)

            c_dissimilarity = 1.0 - c_similarity
            np.fill_diagonal(c_dissimilarity, 0.0)
            c_qubo = build_maxcut_qubo(c_dissimilarity)
            classical_partition, classical_cost = classical_solve_qubo(Q=c_qubo, seed=seed)
            classical_weights = self._weights_from_partition(classical_partition, c_similarity)

            qaoa_circuit_info = {
                "num_qubits": int(q_qubo.shape[0]),
                "qaoa_layers": 1,
                "optimized_params": q_qaoa_result.params,
                "measurement_counts": q_qaoa_result.counts,
                "qubo_cost": q_qaoa_result.cost,
            }
        else:
            quantum_partition = [0] * n_agents
            classical_partition = [0] * n_agents
            quantum_weights = [1.0 / n_agents] * n_agents if n_agents else []
            classical_weights = list(quantum_weights)
            qaoa_circuit_info = None

        selected_policy_weights = "quantum" if config.quantum.use_quantum_weights else "classical"
        selected_weights = quantum_weights if selected_policy_weights == "quantum" else classical_weights

        prev_hash = self._persist_event(
            run_id=run_id,
            event_type="consensus_weights",
            payload={
                "quantum_weights": quantum_weights,
                "classical_weights": classical_weights,
                "selected_weights": selected_weights,
                "selected_policy": selected_policy_weights,
                "quantum_partition": quantum_partition,
                "classical_partition": classical_partition,
                "qaoa_circuit": qaoa_circuit_info,
            },
            prev_hash=prev_hash,
        )

        quantum_baseline_answer = self._pick_final_by_weights(agent_ids, candidate_answers, quantum_weights)
        classical_baseline_answer = self._pick_final_by_weights(agent_ids, candidate_answers, classical_weights)
        final_answer = quantum_baseline_answer if selected_policy_weights == "quantum" else classical_baseline_answer
        
        consensus_duration_ms = int((time.time() - consensus_start_time) * 1000)
        
        prev_hash = self._persist_event(
            run_id=run_id,
            event_type="consensus_completed",
            payload={
                "duration_ms": consensus_duration_ms,
                "selected_policy": selected_policy_weights,
            },
            prev_hash=prev_hash,
        )

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
                logger.warning("[DEBATE] run_id=%s anchor_error=%s", run_id, anchor_error)

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
