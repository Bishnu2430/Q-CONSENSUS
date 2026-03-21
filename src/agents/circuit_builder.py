"""
Quantum circuit construction for Q-CONSENSUS agents.
Builds parameterized single-qubit circuits with RY and RZ gates.
"""

from qiskit import QuantumCircuit
import numpy as np


class CircuitBuilder:
    """
    Constructs parameterized quantum circuits for decision-making agents.
    
    Supports single-qubit circuits with RY (Y-rotation) and RZ (Z-rotation) gates.
    """
    
    def __init__(self, config: dict):
        """
        Initialize CircuitBuilder with configuration.
        
        Args:
            config: Agent configuration dict containing:
                - gate_set: List of allowed gates (e.g., ['RY', 'RZ'])
                - max_circuit_depth: Maximum number of gates
                - qubits_per_agent: Number of qubits (typically 1)
        """
        self.gate_set = config.get('gate_set', ['RY', 'RZ'])
        self.max_depth = config.get('max_circuit_depth', 3)
        self.num_qubits = config.get('qubits_per_agent', 1)
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate configuration parameters."""
        if self.max_depth < 1:
            raise ValueError(f"max_circuit_depth must be >= 1, got {self.max_depth}")
        
        if self.num_qubits < 1:
            raise ValueError(f"qubits_per_agent must be >= 1, got {self.num_qubits}")
        
        allowed_gates = ['RY', 'RZ', 'RX', 'H', 'X', 'Y', 'Z']
        for gate in self.gate_set:
            if gate not in allowed_gates:
                raise ValueError(f"Unsupported gate: {gate}")
    
    def build_single_qubit_circuit(self, 
                                   theta: float,
                                   phi: float = 0.0) -> QuantumCircuit:
        """
        Build single-qubit parameterized circuit.
        
        Circuit structure:
        |0⟩ ──RY(θ)──RZ(φ)──M──
        
        Args:
            theta: Y-rotation angle in radians (0 to π)
            phi: Z-rotation angle in radians (0 to 2π)
            
        Returns:
            QuantumCircuit ready for execution
            
        Raises:
            ValueError: If parameters out of valid range
        """
        # Validate parameters
        if not (0 <= theta <= np.pi):
            raise ValueError(f"theta must be in [0, π], got {theta}")
        
        if not (0 <= phi <= 2 * np.pi):
            raise ValueError(f"phi must be in [0, 2π], got {phi}")
        
        # Create circuit
        qc = QuantumCircuit(1, 1)  # 1 qubit, 1 classical bit
        
        # Apply gates according to gate_set
        if 'RY' in self.gate_set:
            qc.ry(theta, 0)
        
        if 'RZ' in self.gate_set:
            qc.rz(phi, 0)
        
        # Measure qubit to classical bit
        qc.measure(0, 0)
        
        return qc
    
    def validate_circuit(self, circuit: QuantumCircuit) -> bool:
        """
        Verify circuit meets configuration constraints.
        
        Checks:
        - Circuit depth <= max_depth
        - All gates in allowed gate_set
        - Correct number of qubits
        
        Args:
            circuit: QuantumCircuit to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Check depth
        if circuit.depth() > self.max_depth:
            return False
        
        # Check qubit count
        if circuit.num_qubits != self.num_qubits:
            return False
        
        # Check gates
        for instruction in circuit.data:
            gate_name = instruction.operation.name
            # Allow measurement gates
            if gate_name == 'measure':
                continue
            # Check if gate in allowed set
            if gate_name.upper() not in self.gate_set:
                return False
        
        return True
    
    def get_circuit_info(self, circuit: QuantumCircuit) -> dict:
        """
        Extract information about a circuit.
        
        Returns:
            Dict with keys: depth, num_gates, gate_types
        """
        gate_types = [instr.operation.name for instr in circuit.data]
        
        return {
            'depth': circuit.depth(),
            'num_gates': len(circuit.data),
            'gate_types': gate_types,
            'num_qubits': circuit.num_qubits,
            'num_clbits': circuit.num_clbits
        }