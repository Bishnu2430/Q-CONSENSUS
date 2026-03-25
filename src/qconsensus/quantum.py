from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from qiskit import QuantumCircuit

from .quantum_executor import QuantumExecutor


@dataclass(frozen=True)
class QuantumRandomResult:
    bits: List[int]
    seed_used: int


def quantum_random_bits(*, n_bits: int, executor: QuantumExecutor, seed: Optional[int] = None) -> QuantumRandomResult:
    """Generate random bits via quantum measurement (simulated).

    Uses n_bits independent single-qubit H measurements.
    """
    if n_bits < 1:
        raise ValueError("n_bits must be >= 1")

    seed_used = seed if seed is not None else executor.current_seed

    circuits: List[QuantumCircuit] = []
    for _ in range(n_bits):
        qc = QuantumCircuit(1, 1)
        qc.h(0)
        qc.measure(0, 0)
        circuits.append(qc)

    counts_list = executor.execute_batch(circuits, shots=1, seed=seed_used)

    bits: List[int] = []
    for counts in counts_list:
        bit = 1 if counts.get("1", 0) == 1 else 0
        bits.append(bit)

    return QuantumRandomResult(bits=bits, seed_used=seed_used)


def quantum_weights_from_angles(
    *,
    angles: List[float],
    executor: QuantumExecutor,
    shots: int = 256,
    seed: Optional[int] = None,
) -> List[float]:
    """Produce a weight per agent using a single-qubit Ry measurement."""
    if shots < 1:
        raise ValueError("shots must be >= 1")

    seed_used = seed if seed is not None else executor.current_seed

    circuits: List[QuantumCircuit] = []
    for a in angles:
        qc = QuantumCircuit(1, 1)
        qc.ry(float(a), 0)
        qc.measure(0, 0)
        circuits.append(qc)

    counts_list = executor.execute_batch(circuits, shots=shots, seed=seed_used)

    weights: List[float] = []
    for counts in counts_list:
        c1 = counts.get("1", 0)
        weights.append(float(c1 / shots))

    total = float(np.sum(weights))
    if total <= 0:
        return [1.0 / len(weights)] * len(weights)
    return [w / total for w in weights]
