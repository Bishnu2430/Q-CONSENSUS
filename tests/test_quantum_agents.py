"""Unit tests for QuantumAgent."""

import pytest
import numpy as np

from src.agents.quantum_agent import QuantumAgent, initialize_agents


def get_test_config():
    """Standard test configuration."""
    return {
        'gate_set': ['RY', 'RZ'],
        'max_circuit_depth': 3,
        'qubits_per_agent': 1,
        'base_seed': 42,
        'environment_coupling': {
            'enabled': True,
            'coupling_strength': 0.5
        }
    }


def test_agent_initialization():
    """Test QuantumAgent initializes correctly."""
    config = get_test_config()
    agent = QuantumAgent(
        agent_id=0,
        base_theta=np.pi/4,
        base_phi=np.pi/2,
        config=config
    )
    
    assert agent.agent_id == 0
    assert agent.base_theta == np.pi/4
    assert agent.base_phi == np.pi/2


def test_agent_measure():
    """Test agent measurement produces valid results."""
    config = get_test_config()
    agent = QuantumAgent(
        agent_id=0,
        base_theta=np.pi/2,  # Equal superposition
        base_phi=0.0,
        config=config
    )
    
    result = agent.measure(env_theta=0.5, shots=1000)
    
    # Check result structure
    assert 'agent_id' in result
    assert 'probability' in result
    assert 'std_error' in result
    assert 'counts' in result
    assert 'shots' in result
    
    # Check values are reasonable
    assert 0 <= result['probability'] <= 1
    assert result['std_error'] >= 0
    assert result['shots'] == 1000


def test_probability_estimation():
    """Test probability estimates are reasonable."""
    config = get_test_config()
    
    # Agent with theta=0 should bias toward |0⟩
    agent_0 = QuantumAgent(0, base_theta=0.0, base_phi=0.0, config=config)
    result_0 = agent_0.measure(env_theta=0.0, shots=1000)
    
    # Should have low probability of measuring '1'
    assert result_0['probability'] < 0.2
    
    # Agent with theta=π should bias toward |1⟩
    agent_1 = QuantumAgent(1, base_theta=np.pi, base_phi=0.0, config=config)
    result_1 = agent_1.measure(env_theta=0.0, shots=1000)
    
    # Should have high probability of measuring '1'
    assert result_1['probability'] > 0.8


def test_initialize_agents():
    """Test batch agent initialization."""
    config = get_test_config()
    N = 5
    
    agents = initialize_agents(N, config)
    
    assert len(agents) == N
    
    # Check uniform spacing
    for i, agent in enumerate(agents):
        assert agent.agent_id == i
        expected_theta = (i / N) * np.pi
        assert np.isclose(agent.base_theta, expected_theta)


def test_environment_coupling():
    """Test that environment parameter affects circuit."""
    config = get_test_config()
    agent = QuantumAgent(0, base_theta=np.pi/4, base_phi=0.0, config=config)
    
    # Measure with different environment values
    result_low = agent.measure(env_theta=0.0, shots=1000)
    result_high = agent.measure(env_theta=1.0, shots=1000)
    
    # Probabilities should be different
    # (exact values depend on coupling strength)
    assert result_low['probability'] != result_high['probability']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])