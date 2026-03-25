"""Quantum circuit execution using Qiskit Aer simulator.

This is a minimal, reusable execution layer used by the v2 prototype.
"""

from __future__ import annotations

import hashlib
from typing import Dict, Optional

from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator


class QuantumExecutor:
    """Executes quantum circuits using Qiskit Aer simulator."""

    def __init__(self, config: dict):
        self.backend_name = config.get("simulator_backend", "qasm_simulator")
        self.base_seed = config.get("base_seed", 42)
        self.simulator = AerSimulator()
        self.current_seed = self.base_seed

    def execute(self, circuit: QuantumCircuit, shots: int, seed: Optional[int] = None) -> Dict[str, int]:
        if shots < 1:
            raise ValueError(f"shots must be >= 1, got {shots}")

        execution_seed = seed if seed is not None else self.current_seed
        transpiled = transpile(circuit, self.simulator)

        job = self.simulator.run(transpiled, shots=shots, seed_simulator=execution_seed)
        result = job.result()
        counts = result.get_counts()

        if circuit.num_qubits == 1:
            counts.setdefault("0", 0)
            counts.setdefault("1", 0)

        return counts

    def execute_batch(self, circuits: list[QuantumCircuit], shots: int, seed: Optional[int] = None) -> list[Dict[str, int]]:
        if not circuits:
            return []

        transpiled = transpile(circuits, self.simulator)
        execution_seed = seed if seed is not None else self.current_seed

        job = self.simulator.run(transpiled, shots=shots, seed_simulator=execution_seed)
        result = job.result()

        all_counts: list[Dict[str, int]] = []
        for i, circuit in enumerate(circuits):
            counts = result.get_counts(i)
            if circuit.num_qubits == 1:
                counts.setdefault("0", 0)
                counts.setdefault("1", 0)
            all_counts.append(counts)

        return all_counts

    def set_seed(self, seed: int) -> None:
        self.current_seed = seed

    def get_seed_from_config(self, config_dict: dict) -> int:
        import json

        config_str = json.dumps(config_dict, sort_keys=True)
        hash_obj = hashlib.sha256(config_str.encode())
        return int(hash_obj.hexdigest()[:8], 16)
