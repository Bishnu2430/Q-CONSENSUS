"""Quantum kernel similarity estimation for debate answers.

This gives the quantum layer something with real influence on the debate: a
similarity score between agents' answers, used both to weight the final
consensus (src/qconsensus/debate.py) and to decide whether the debate has
already converged and further rounds are unnecessary.

Honesty note: there is no learned text embedding model anywhere in this
stack, so `text_to_angles` uses a hashed bag-of-words feature map (a
legitimate, if simple, classical preprocessing step for a quantum feature
map) rather than a semantic embedding. The quantum part is real: two texts
are encoded into quantum states via parameterized rotations, and their
similarity is estimated from the measured overlap of those states (a
fidelity/inverse-circuit test), which is the same technique used in quantum
kernel methods (QSVM-style kernels). On the Aer simulator this is not faster
than a classical kernel -- the point is that the number it returns is
actually computed by the quantum circuit, not decorated randomness.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional, Tuple

import numpy as np
from qiskit import QuantumCircuit

from .quantum_executor import QuantumExecutor

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


def text_to_angles(text: str, n_qubits: int) -> List[float]:
    """Hash tokens of `text` into `n_qubits` buckets and scale to [0, pi].

    Deterministic: the same text always maps to the same angles, so the
    resulting quantum state -- and therefore any kernel computed from it --
    is reproducible across runs and replay.

    Normalized by the *largest* bucket, not the total token count. Dividing
    by total token count keeps every angle small for any normal-length
    paragraph (a bucket rarely holds more than ~15% of all tokens), and
    RY(theta) barely moves the qubit away from |0> for small theta -- so
    the fidelity test below stayed pinned near 1.0 for any two texts of
    similar length, regardless of actual content (verified empirically:
    real, clearly-different agent answers were scoring 0.92-1.0). Scaling
    so the dominant bucket reaches pi gives the rotations enough dynamic
    range to actually diverge between different texts.
    """
    if n_qubits < 1:
        raise ValueError("n_qubits must be >= 1")

    tokens = _tokenize(text)
    if not tokens:
        return [0.0] * n_qubits

    buckets = np.zeros(n_qubits, dtype=float)
    for tok in tokens:
        idx = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16) % n_qubits
        buckets[idx] += 1.0

    peak = float(buckets.max())
    if peak <= 0:
        return [0.0] * n_qubits
    return [float(x / peak * np.pi) for x in buckets]


def _feature_map_circuit(angles: List[float]) -> QuantumCircuit:
    n = len(angles)
    qc = QuantumCircuit(n)
    for i, angle in enumerate(angles):
        qc.ry(angle, i)
    for i in range(n - 1):
        qc.cx(i, i + 1)
    for i, angle in enumerate(angles):
        qc.rz(angle, i)
    return qc


def quantum_kernel_similarity(
    *,
    text_a: str,
    text_b: str,
    executor: QuantumExecutor,
    n_qubits: int = 4,
    shots: int = 512,
    seed: Optional[int] = None,
) -> float:
    """Estimate |<phi(a)|phi(b)>|^2 via an inverse-circuit fidelity test.

    Applying phi(a) then the inverse of phi(b) to |0...0> and measuring the
    probability of the all-zero outcome recovers the squared state overlap
    between the two feature-mapped states. Returns a value in [0, 1].
    """
    if text_a == text_b:
        return 1.0

    seed_used = seed if seed is not None else executor.current_seed
    angles_a = text_to_angles(text_a, n_qubits)
    angles_b = text_to_angles(text_b, n_qubits)

    qc = _feature_map_circuit(angles_a)
    qc.compose(_feature_map_circuit(angles_b).inverse(), inplace=True)
    qc.measure_all()

    counts = executor.execute(qc, shots=shots, seed=seed_used)
    zero_state = "0" * n_qubits

    hits = 0
    for bitstring, c in counts.items():
        cleaned = bitstring.replace(" ", "")
        if cleaned == zero_state or cleaned.endswith(zero_state):
            hits += c

    return float(hits / shots) if shots > 0 else 0.0


def classical_text_similarity(text_a: str, text_b: str) -> float:
    """Jaccard word-overlap similarity -- the classical baseline kernel."""
    if text_a == text_b:
        return 1.0

    a = set(_tokenize(text_a))
    b = set(_tokenize(text_b))
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return float(len(a & b) / len(a | b))


def pairwise_similarity_matrix(
    *,
    agent_ids: List[str],
    texts: Dict[str, str],
    kind: str,
    executor: Optional[QuantumExecutor] = None,
    n_qubits: int = 4,
    shots: int = 512,
    seed: Optional[int] = None,
) -> np.ndarray:
    """Build an n x n symmetric similarity matrix over `agent_ids`.

    `kind` is "quantum" (requires `executor`) or "classical".
    """
    n = len(agent_ids)
    matrix = np.zeros((n, n), dtype=float)

    for i in range(n):
        matrix[i, i] = 1.0
        for j in range(i + 1, n):
            text_a = texts.get(agent_ids[i], "")
            text_b = texts.get(agent_ids[j], "")
            if kind == "quantum":
                if executor is None:
                    raise ValueError("executor is required for kind='quantum'")
                sim = quantum_kernel_similarity(
                    text_a=text_a,
                    text_b=text_b,
                    executor=executor,
                    n_qubits=n_qubits,
                    shots=shots,
                    seed=seed,
                )
            elif kind == "classical":
                sim = classical_text_similarity(text_a, text_b)
            else:
                raise ValueError(f"unknown kind: {kind}")
            matrix[i, j] = sim
            matrix[j, i] = sim

    return matrix


def average_pairwise_similarity(matrix: np.ndarray) -> float:
    """Mean of the off-diagonal entries of a similarity matrix."""
    n = matrix.shape[0]
    if n < 2:
        return 1.0
    off_diag_sum = float(np.sum(matrix)) - float(np.trace(matrix))
    count = n * (n - 1)
    return off_diag_sum / count if count > 0 else 1.0
