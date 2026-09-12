"""A small, self-contained QAOA solver for QUBO problems.

This is the piece that turns "quantum" from a buzzword into an algorithm
with a real, checkable output: given a QUBO (minimize x^T Q x over binary
x), it builds a parameterized QAOA circuit, optimizes its parameters
classically against measured expectation values from the Aer simulator, and
returns the best bitstring found. A brute-force/local-search classical
solver for the same QUBO is included alongside it, so every quantum decision
in the debate has a like-for-like classical baseline (matching the existing
quantum-vs-classical comparison pattern in metrics.py).

Scale note: qubit count equals the QUBO size. This is intended for the
small (<= ~8 variable) decisions that come up in a debate -- e.g. one binary
variable per agent -- not large combinatorial problems.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from qiskit import QuantumCircuit
from scipy.optimize import minimize

from .quantum_executor import QuantumExecutor


@dataclass(frozen=True)
class QaoaResult:
    bitstring: List[int]
    cost: float
    seed_used: int
    params: List[float]
    counts: Dict[str, int]


def build_maxcut_qubo(weights: np.ndarray) -> np.ndarray:
    """QUBO Q such that argmin x^T Q x maximizes the weighted cut.

    `weights` is a symmetric n x n matrix of non-negative edge weights
    (zero diagonal). Splitting nodes into two groups to maximize the total
    weight of edges *cut* between the groups is the classic Max-Cut problem
    -- NP-hard in general, and the textbook first application of QAOA
    (Farhi, Goldstone & Gutmann 2014). Used here to cluster agents by
    dissimilarity: cutting apart the most dissimilar pairs concentrates
    mutually similar agents into the same partition.
    """
    n = weights.shape[0]
    Q = np.zeros((n, n))
    for i in range(n):
        Q[i, i] = -float(np.sum(weights[i, :]))
    for i in range(n):
        for j in range(i + 1, n):
            Q[i, j] = 2.0 * float(weights[i, j])
    return Q


def _qubo_cost(bits: List[int], Q: np.ndarray) -> float:
    x = np.array(bits, dtype=float)
    return float(x @ Q @ x)


def _apply_cost_unitary(qc: QuantumCircuit, Q: np.ndarray, gamma: float) -> None:
    n = Q.shape[0]
    for i in range(n):
        if Q[i, i] != 0:
            qc.rz(2 * gamma * Q[i, i], i)
    for i in range(n):
        for j in range(i + 1, n):
            w = Q[i, j] + Q[j, i]
            if w != 0:
                qc.cx(i, j)
                qc.rz(2 * gamma * w, j)
                qc.cx(i, j)


def _apply_mixer(qc: QuantumCircuit, beta: float) -> None:
    for i in range(qc.num_qubits):
        qc.rx(2 * beta, i)


def _build_qaoa_circuit(Q: np.ndarray, params: List[float], p: int) -> QuantumCircuit:
    n = Q.shape[0]
    qc = QuantumCircuit(n, n)
    qc.h(range(n))
    for layer in range(p):
        gamma = params[2 * layer]
        beta = params[2 * layer + 1]
        _apply_cost_unitary(qc, Q, gamma)
        _apply_mixer(qc, beta)
    qc.measure(range(n), range(n))
    return qc


def _bits_from_bitstring(bitstring: str, n: int) -> List[int]:
    cleaned = bitstring.replace(" ", "")
    bits = [int(b) for b in cleaned[::-1]]
    if len(bits) < n:
        bits = bits + [0] * (n - len(bits))
    return bits[:n]


def solve_qubo_qaoa(
    *,
    Q: np.ndarray,
    executor: QuantumExecutor,
    p: int = 1,
    shots: int = 256,
    maxiter: int = 20,
    seed: Optional[int] = None,
) -> QaoaResult:
    n = Q.shape[0]
    if n < 1:
        raise ValueError("Q must be at least 1x1")
    seed_used = seed if seed is not None else executor.current_seed

    def expected_cost(params: np.ndarray) -> float:
        qc = _build_qaoa_circuit(Q, list(params), p)
        counts = executor.execute(qc, shots=shots, seed=seed_used)
        total = sum(counts.values())
        if total == 0:
            return 0.0
        exp = 0.0
        for bitstring, c in counts.items():
            bits = _bits_from_bitstring(bitstring, n)
            exp += (c / total) * _qubo_cost(bits, Q)
        return exp

    rng = np.random.default_rng(seed_used)
    x0 = rng.uniform(0, np.pi, size=2 * p)

    result = minimize(expected_cost, x0, method="COBYLA", options={"maxiter": maxiter})
    best_params = [float(v) for v in result.x]

    final_qc = _build_qaoa_circuit(Q, best_params, p)
    final_counts = executor.execute(final_qc, shots=max(shots, 512), seed=seed_used)

    best_bits: Optional[List[int]] = None
    best_cost = float("inf")
    for bitstring in final_counts:
        bits = _bits_from_bitstring(bitstring, n)
        c = _qubo_cost(bits, Q)
        if c < best_cost:
            best_cost = c
            best_bits = bits

    if best_bits is None:
        best_bits = [0] * n
        best_cost = _qubo_cost(best_bits, Q)

    return QaoaResult(
        bitstring=best_bits,
        cost=best_cost,
        seed_used=seed_used,
        params=best_params,
        counts=final_counts,
    )


def classical_solve_qubo(*, Q: np.ndarray, seed: int) -> Tuple[List[int], float]:
    """Brute force for small n, randomized local search otherwise."""
    n = Q.shape[0]
    if n <= 16:
        best_bits: List[int] = [0] * n
        best_cost = float("inf")
        for combo in itertools.product([0, 1], repeat=n):
            c = _qubo_cost(list(combo), Q)
            if c < best_cost:
                best_cost = c
                best_bits = list(combo)
        return best_bits, best_cost

    rng = np.random.default_rng(seed)
    bits = [int(x) for x in rng.integers(0, 2, size=n)]
    best_cost = _qubo_cost(bits, Q)
    for _ in range(500):
        i = int(rng.integers(0, n))
        candidate = bits.copy()
        candidate[i] = 1 - candidate[i]
        c = _qubo_cost(candidate, Q)
        if c < best_cost:
            bits, best_cost = candidate, c
    return bits, best_cost
