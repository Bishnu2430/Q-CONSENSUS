"""Unit tests for QuantumExecutor."""

import pytest
from qiskit import QuantumCircuit

from src.agents.quantum_executor import QuantumExecutor


def test_executor_initialization():
    """Test QuantumExecutor initializes correctly."""
    config = {'base_seed': 123}
    executor = QuantumExecutor(config)
    
    assert executor.current_seed == 123
    assert executor.base_seed == 123


def test_execute_simple_circuit():
    """Test executing a simple quantum circuit."""
    config = {'base_seed': 42}
    executor = QuantumExecutor(config)
    
    # Create simple circuit: |0⟩ → X → M (should always measure 1)
    qc = QuantumCircuit(1, 1)
    qc.x(0)  # X gate flips |0⟩ to |1⟩
    qc.measure(0, 0)
    
    counts = executor.execute(qc, shots=100, seed=42)
    
    # Should get ~100 counts of '1', ~0 counts of '0'
    assert counts['1'] == 100
    assert counts['0'] == 0


def test_reproducibility():
    """Test that same seed produces same results."""
    config = {'base_seed': 42}
    executor = QuantumExecutor(config)
    
    # Create circuit with superposition
    qc = QuantumCircuit(1, 1)
    qc.h(0)  # Hadamard: creates superposition
    qc.measure(0, 0)
    
    # Run twice with same seed
    counts1 = executor.execute(qc, shots=1000, seed=123)
    counts2 = executor.execute(qc, shots=1000, seed=123)
    
    # Results should be identical
    assert counts1 == counts2


def test_batch_execution():
    """Test executing multiple circuits at once."""
    config = {'base_seed': 42}
    executor = QuantumExecutor(config)
    
    # Create two different circuits
    qc1 = QuantumCircuit(1, 1)
    qc1.x(0)
    qc1.measure(0, 0)
    
    qc2 = QuantumCircuit(1, 1)
    qc2.measure(0, 0)  # Identity, always '0'
    
    results = executor.execute_batch([qc1, qc2], shots=100, seed=42)
    
    assert len(results) == 2
    assert results[0]['1'] == 100  # First circuit
    assert results[1]['0'] == 100  # Second circuit


if __name__ == '__main__':
    pytest.main([__file__, '-v'])