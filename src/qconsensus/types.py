from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    display_name: str
    system_prompt: str


@dataclass(frozen=True)
class QuantumPolicyConfig:
    use_quantum_randomness: bool = True
    use_quantum_weights: bool = True
    use_quantum_scheduling: bool = True
    shots_randomness: int = 1
    shots_weights: int = 256
    shots_scheduling: int = 256

    # Quantum-kernel-driven early stop: if agents' round-0 answers already
    # cluster tightly (avg pairwise similarity >= threshold), skip the
    # cross-critique/self-revision rounds. Off by default so existing
    # callers keep their configured max_rounds unless they opt in.
    use_quantum_convergence: bool = False
    convergence_similarity_threshold: float = 0.82
    shots_convergence: int = 256
    kernel_qubits: int = 4


@dataclass(frozen=True)
class DebateConfig:
    agents: List[AgentSpec]
    max_rounds: int = 3
    quantum: QuantumPolicyConfig = QuantumPolicyConfig()


@dataclass(frozen=True)
class DebateMessage:
    run_id: str
    agent_id: str
    role: str
    content: str
    round_idx: int


@dataclass(frozen=True)
class DebateResult:
    run_id: str
    final_answer: str
    messages: List[DebateMessage]
    commitment: str
    anchor_tx_hash: Optional[str]
