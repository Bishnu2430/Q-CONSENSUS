from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import List, Optional

import numpy as np
from qiskit import QuantumCircuit

from .quantum_executor import QuantumExecutor


@dataclass(frozen=True)
class QuantumRandomResult:
    bits: List[int]
    seed_used: int


def classical_random_bits(*, n_bits: int, seed: int) -> List[int]:
    if n_bits < 1:
        raise ValueError("n_bits must be >= 1")
    rng = np.random.default_rng(seed)
    return [int(x) for x in rng.integers(0, 2, size=n_bits)]


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


def _phase_from_seed(seed: int, idx: int) -> float:
    digest = hashlib.sha256(f"{seed}:{idx}".encode("utf-8")).hexdigest()
    raw = int(digest[:8], 16)
    return float((raw % 6283) / 1000.0)


def quantum_schedule_scores(
    *,
    n_agents: int,
    executor: QuantumExecutor,
    shots: int = 256,
    seed: Optional[int] = None,
) -> List[float]:
    if n_agents < 1:
        raise ValueError("n_agents must be >= 1")

    seed_used = seed if seed is not None else executor.current_seed
    circuits: List[QuantumCircuit] = []
    for i in range(n_agents):
        phase = _phase_from_seed(seed_used, i)
        qc = QuantumCircuit(1, 1)
        qc.h(0)
        qc.rz(phase, 0)
        qc.h(0)
        qc.measure(0, 0)
        circuits.append(qc)

    counts_list = executor.execute_batch(circuits, shots=shots, seed=seed_used)
    return [float(c.get("1", 0) / shots) for c in counts_list]


def classical_schedule_scores(*, n_agents: int, seed: int) -> List[float]:
    if n_agents < 1:
        raise ValueError("n_agents must be >= 1")
    rng = np.random.default_rng(seed)
    return [float(x) for x in rng.random(n_agents)]
