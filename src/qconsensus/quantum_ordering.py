"""Diversity-driven agent ordering via QAOA Max-Cut bipartition.

Both the round-0 speaking order and the critique/revision scheduling order
reuse the same mechanism: compute pairwise dissimilarity between the
relevant texts (agent system prompts for round 0, since no answer content
exists yet; agents' own initial answers for the later rounds, once it
does), solve a Max-Cut QUBO via QAOA to split agents into two mutually
dissimilar clusters, then interleave the clusters so adjacent speakers tend
to represent different perspectives. This replaces the previous
sort-by-random-quantum-bit ordering, which had no real signal behind it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from .quantum_executor import QuantumExecutor
from .quantum_kernel import pairwise_similarity_matrix
from .quantum_qaoa import build_maxcut_qubo, classical_solve_qubo, solve_qubo_qaoa


@dataclass(frozen=True)
class DiversityOrderResult:
    quantum_order: List[int]
    classical_order: List[int]
    quantum_partition: List[int]
    classical_partition: List[int]
    quantum_similarity: List[List[float]]
    classical_similarity: List[List[float]]


def _interleave_partition(partition: List[int]) -> List[int]:
    group0 = [i for i, label in enumerate(partition) if label == 0]
    group1 = [i for i, label in enumerate(partition) if label == 1]

    order: List[int] = []
    for a, b in zip(group0, group1):
        order.append(a)
        order.append(b)

    shorter_len = min(len(group0), len(group1))
    leftover = group0[shorter_len:] or group1[shorter_len:]
    order.extend(leftover)
    return order


def diversity_order(
    *,
    agent_ids: List[str],
    texts: Dict[str, str],
    executor: QuantumExecutor,
    n_qubits: int = 4,
    shots: int = 256,
    maxiter: int = 20,
    seed: Optional[int] = None,
) -> DiversityOrderResult:
    n = len(agent_ids)
    if n < 2:
        order = list(range(n))
        identity = [[1.0] * n for _ in range(n)]
        return DiversityOrderResult(
            quantum_order=order,
            classical_order=order,
            quantum_partition=[0] * n,
            classical_partition=[0] * n,
            quantum_similarity=identity,
            classical_similarity=identity,
        )

    q_similarity = pairwise_similarity_matrix(
        agent_ids=agent_ids,
        texts=texts,
        kind="quantum",
        executor=executor,
        n_qubits=n_qubits,
        shots=shots,
        seed=seed,
    )
    c_similarity = pairwise_similarity_matrix(agent_ids=agent_ids, texts=texts, kind="classical")

    q_dissimilarity = 1.0 - q_similarity
    np.fill_diagonal(q_dissimilarity, 0.0)
    q_qubo = build_maxcut_qubo(q_dissimilarity)
    q_result = solve_qubo_qaoa(
        Q=q_qubo, executor=executor, p=1, shots=shots, maxiter=maxiter, seed=seed
    )
    quantum_partition = q_result.bitstring

    c_dissimilarity = 1.0 - c_similarity
    np.fill_diagonal(c_dissimilarity, 0.0)
    c_qubo = build_maxcut_qubo(c_dissimilarity)
    classical_partition, _ = classical_solve_qubo(Q=c_qubo, seed=seed or 0)

    return DiversityOrderResult(
        quantum_order=_interleave_partition(quantum_partition),
        classical_order=_interleave_partition(classical_partition),
        quantum_partition=quantum_partition,
        classical_partition=classical_partition,
        quantum_similarity=q_similarity.tolist(),
        classical_similarity=c_similarity.tolist(),
    )
