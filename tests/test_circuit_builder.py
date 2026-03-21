"""Unit tests for CircuitBuilder."""

import pytest
import numpy as np
from qiskit import QuantumCircuit

from src.agents.circuit_builder import CircuitBuilder


def test_circuit_builder_initialization():
    """Test CircuitBuilder initializes correctly."""
    config = {
        'gate_set': ['RY', 'RZ'],
        'max_circuit_depth': 3,
        'qubits_per_agent': 1
    }
    
    builder = CircuitBuilder(config)
    
    assert builder.gate_set == ['RY', 'RZ']
    assert builder.max_depth == 3
    assert builder.num_qubits == 1


def test_build_single_qubit_circuit():
    """Test building a basic single-qubit circuit."""
    config = {
        'gate_set': ['RY', 'RZ'],
        'max_circuit_depth': 3,
        'qubits_per_agent': 1
    }
    
    builder = CircuitBuilder(config)
    circuit = builder.build_single_qubit_circuit(theta=np.pi/4, phi=np.pi/2)
    
    # Check circuit structure
    assert circuit.num_qubits == 1
    assert circuit.num_clbits == 1
    assert circuit.depth() <= 3
    
    # Circuit should be valid
    assert builder.validate_circuit(circuit)


def test_parameter_validation():
    """Test that invalid parameters are rejected."""
    config = {'gate_set': ['RY', 'RZ'], 'max_circuit_depth': 3, 'qubits_per_agent': 1}
    builder = CircuitBuilder(config)
    
    # theta out of range
    with pytest.raises(ValueError):
        builder.build_single_qubit_circuit(theta=4.0, phi=0.0)
    
    # phi out of range
    with pytest.raises(ValueError):
        builder.build_single_qubit_circuit(theta=1.0, phi=10.0)


def test_circuit_info():
    """Test extracting circuit information."""
    config = {'gate_set': ['RY', 'RZ'], 'max_circuit_depth': 3, 'qubits_per_agent': 1}
    builder = CircuitBuilder(config)
    
    circuit = builder.build_single_qubit_circuit(theta=np.pi/2, phi=np.pi)
    info = builder.get_circuit_info(circuit)
    
    assert 'depth' in info
    assert 'num_gates' in info
    assert 'gate_types' in info
    assert info['num_qubits'] == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])