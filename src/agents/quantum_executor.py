"""
Quantum circuit execution using Qiskit Aer simulator.
Provides controlled, reproducible execution of quantum circuits.
"""

from qiskit import transpile
from qiskit_aer import AerSimulator
from qiskit import QuantumCircuit
from typing import Dict, Optional
import hashlib


class QuantumExecutor:
    """
    Executes quantum circuits using Qiskit Aer simulator.
    
    Provides controlled execution with seed management for reproducibility.
    """
    
    def __init__(self, config: dict):
        """
        Initialize QuantumExecutor.
        
        Args:
            config: Configuration dict containing:
                - simulator_backend: 'qasm_simulator' (default)
                - base_seed: Base random seed for reproducibility
        """
        self.backend_name = config.get('simulator_backend', 'qasm_simulator')
        self.base_seed = config.get('base_seed', 42)
        
        # Initialize Aer simulator
        self.simulator = AerSimulator()
        
        # Current seed (can be modified)
        self.current_seed = self.base_seed
    
    def execute(self, 
                circuit: QuantumCircuit,
                shots: int,
                seed: Optional[int] = None) -> Dict[str, int]:
        """
        Execute quantum circuit on simulator.
        
        Args:
            circuit: QuantumCircuit to execute
            shots: Number of measurement shots
            seed: Random seed (if None, uses current_seed)
            
        Returns:
            Dict mapping outcomes to counts, e.g., {'0': 600, '1': 400}
            
        Raises:
            ValueError: If shots < 1
        """
        if shots < 1:
            raise ValueError(f"shots must be >= 1, got {shots}")
        
        # Use provided seed or current seed
        execution_seed = seed if seed is not None else self.current_seed
        
        # Transpile circuit for simulator
        transpiled = transpile(circuit, self.simulator)
        
        # Execute with seed
        job = self.simulator.run(
            transpiled,
            shots=shots,
            seed_simulator=execution_seed
        )
        
        # Get results
        result = job.result()
        counts = result.get_counts()
        
        # Ensure all possible outcomes are in counts (even if 0)
        # For single qubit: ensure both '0' and '1' keys exist
        if circuit.num_qubits == 1:
            counts.setdefault('0', 0)
            counts.setdefault('1', 0)
        
        return counts
    
    def execute_batch(self,
                     circuits: list[QuantumCircuit],
                     shots: int,
                     seed: Optional[int] = None) -> list[Dict[str, int]]:
        """
        Execute multiple circuits (more efficient than individual execution).
        
        Args:
            circuits: List of QuantumCircuits
            shots: Number of shots per circuit
            seed: Base random seed
            
        Returns:
            List of count dicts, one per circuit
        """
        if not circuits:
            return []
        
        # Transpile all circuits
        transpiled = transpile(circuits, self.simulator)
        
        # Execute batch
        execution_seed = seed if seed is not None else self.current_seed
        job = self.simulator.run(
            transpiled,
            shots=shots,
            seed_simulator=execution_seed
        )
        
        # Get all results
        result = job.result()
        all_counts = []
        
        for i in range(len(circuits)):
            counts = result.get_counts(i)
            # Ensure all outcomes present
            if circuits[i].num_qubits == 1:
                counts.setdefault('0', 0)
                counts.setdefault('1', 0)
            all_counts.append(counts)
        
        return all_counts
    
    def set_seed(self, seed: int):
        """Update random seed for subsequent executions."""
        self.current_seed = seed
    
    def get_seed_from_config(self, config_dict: dict) -> int:
        """
        Generate deterministic seed from configuration.
        
        Uses hash of config to ensure same config → same seed.
        
        Args:
            config_dict: Configuration dictionary
            
        Returns:
            Seed value (32-bit integer)
        """
        import json
        config_str = json.dumps(config_dict, sort_keys=True)
        hash_obj = hashlib.sha256(config_str.encode())
        # Take first 32 bits of hash
        seed = int(hash_obj.hexdigest()[:8], 16)
        return seed