"""Comprehensive tests for agent layer."""

import pytest
import numpy as np

from src.agents import QuantumAgent, initialize_agents, CircuitBuilder, QuantumExecutor


class TestAgentLayer:
    """Integration tests for complete agent layer."""
    
    @pytest.fixture
    def config(self):
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
    
    def test_full_agent_workflow(self, config):
        """Test complete agent execution workflow."""
        # Initialize agent
        agent = QuantumAgent(
            agent_id=0,
            base_theta=np.pi/2,
            base_phi=0.0,
            config=config
        )
        
        # Measure with environment
        env_theta = 0.3
        shots = 1000
        
        result = agent.measure(env_theta, shots)
        
        # Verify complete result
        assert result['agent_id'] == 0
        assert 0 <= result['probability'] <= 1
        assert result['std_error'] > 0
        assert result['shots'] == shots
        assert 'circuit_params' in result
    
    def test_multiple_agents(self, config):
        """Test multiple agents can coexist and execute."""
        N = 10
        agents = initialize_agents(N, config)
        
        # Run all agents
        results = []
        env_theta = 0.5
        
        for agent in agents:
            result = agent.measure(env_theta, shots=1000)
            results.append(result)
        
        # Should have N results
        assert len(results) == N
        
        # Each agent should have unique ID
        agent_ids = [r['agent_id'] for r in results]
        assert agent_ids == list(range(N))
        
        # Probabilities should vary (due to different parameters)
        probabilities = [r['probability'] for r in results]
        assert len(set(probabilities)) > 1  # Not all same
    
    def test_variance_decreases_with_shots(self, config):
        """Test that standard error decreases with more shots."""
        agent = QuantumAgent(0, np.pi/4, 0.0, config)
        
        # Measure with different shot counts
        result_100 = agent.measure(0.5, shots=100)
        result_10000 = agent.measure(0.5, shots=10000)
        
        # Standard error should be lower with more shots
        assert result_10000['std_error'] < result_100['std_error']
    
    def test_reproducibility_with_seed(self, config):
        """Test that results are reproducible with same seed."""
        agent1 = QuantumAgent(0, np.pi/3, 0.0, config)
        agent2 = QuantumAgent(0, np.pi/3, 0.0, config)
        
        # Both use same seed (from config)
        result1 = agent1.measure(0.5, shots=1000)
        result2 = agent2.measure(0.5, shots=1000)
        
        # Results should be identical
        assert result1['probability'] == result2['probability']
        assert result1['counts'] == result2['counts']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])