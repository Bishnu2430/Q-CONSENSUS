"""
Quantum agent for Q-CONSENSUS multi-agent decision system.
Each agent makes probabilistic binary decisions via quantum measurement.
"""

import numpy as np
from typing import Dict

from .circuit_builder import CircuitBuilder
from .quantum_executor import QuantumExecutor


class QuantumAgent:
    """
    Individual quantum decision-making agent.
    
    Uses parameterized quantum circuit to produce probabilistic binary decisions.
    Parameters are fixed at initialization (no learning).
    """
    
    def __init__(self,
                 agent_id: int,
                 base_theta: float,
                 base_phi: float,
                 config: dict):
        """
        Initialize quantum agent.
        
        Args:
            agent_id: Unique agent identifier (0 to N-1)
            base_theta: Base Y-rotation angle (radians, 0 to π)
            base_phi: Base Z-rotation angle (radians, 0 to 2π)
            config: Agent configuration dict
        """
        self.agent_id = agent_id
        self.base_theta = base_theta
        self.base_phi = base_phi
        self.config = config
        
        # Initialize components
        self.circuit_builder = CircuitBuilder(config)
        self.executor = QuantumExecutor(config)
        
        # Validate parameters
        self._validate_parameters()
    
    def _validate_parameters(self):
        """Validate agent parameters are in valid ranges."""
        if not (0 <= self.base_theta <= np.pi):
            raise ValueError(
                f"Agent {self.agent_id}: base_theta must be in [0, π], "
                f"got {self.base_theta}"
            )
        
        if not (0 <= self.base_phi <= 2 * np.pi):
            raise ValueError(
                f"Agent {self.agent_id}: base_phi must be in [0, 2π], "
                f"got {self.base_phi}"
            )
    
    def build_circuit(self, env_theta: float) -> 'QuantumCircuit':
        """
        Build quantum circuit for given environment parameter.
        
        Couples environment to circuit parameters using linear scaling:
        θ_circuit = base_theta + α * env_theta
        
        Where α is coupling strength from config (default 0.5).
        
        Args:
            env_theta: Environment parameter (0 to 1)
            
        Returns:
            QuantumCircuit ready for execution
        """
        # Get coupling strength from config
        coupling_enabled = self.config.get('environment_coupling', {}).get('enabled', False)
        
        if coupling_enabled:
            alpha = self.config.get('environment_coupling', {}).get('coupling_strength', 0.5)
            # Couple environment to theta parameter
            theta_circuit = self.base_theta + alpha * env_theta * np.pi
            # Clamp to valid range
            theta_circuit = np.clip(theta_circuit, 0, np.pi)
        else:
            theta_circuit = self.base_theta
        
        # Build circuit
        circuit = self.circuit_builder.build_single_qubit_circuit(
            theta=theta_circuit,
            phi=self.base_phi
        )
        
        return circuit
    
    def measure(self, env_theta: float, shots: int) -> Dict:
        """
        Execute quantum circuit and return measurement results.
        
        This is the main decision-making method.
        
        Args:
            env_theta: Environment parameter (0 to 1)
            shots: Number of measurement shots
            
        Returns:
            Dict containing:
                - agent_id: int
                - counts: Dict[str, int] (e.g., {'0': 600, '1': 400})
                - probability: float (P(outcome='1'))
                - std_error: float (standard error of probability estimate)
                - shots: int
                - circuit_params: Dict (theta, phi values used)
        """
        # Build circuit for this environment
        circuit = self.build_circuit(env_theta)
        
        # Execute circuit
        counts = self.executor.execute(circuit, shots=shots)
        
        # Process results
        result = self._process_results(counts, shots, env_theta)
        
        return result
    
    def _process_results(self, 
                        counts: Dict[str, int],
                        shots: int,
                        env_theta: float) -> Dict:
        """
        Convert raw counts to probability estimates.
        
        Computes:
        - p̂ = count('1') / total_shots
        - σ = √(p̂(1-p̂) / shots)  [standard error]
        
        Args:
            counts: Raw measurement counts
            shots: Total number of shots
            env_theta: Environment parameter used
            
        Returns:
            Processed measurement result dict
        """
        # Extract counts
        count_0 = counts.get('0', 0)
        count_1 = counts.get('1', 0)
        
        # Verify shot count
        total = count_0 + count_1
        if total != shots:
            raise ValueError(
                f"Agent {self.agent_id}: Count mismatch. "
                f"Expected {shots} shots, got {total}"
            )
        
        # Compute probability estimate: p̂ = count_1 / shots
        p_hat = count_1 / shots
        
        # Compute standard error: σ = √(p̂(1-p̂) / K)
        std_error = np.sqrt(p_hat * (1 - p_hat) / shots)
        
        # Get circuit parameters used
        coupling_enabled = self.config.get('environment_coupling', {}).get('enabled', False)
        if coupling_enabled:
            alpha = self.config.get('environment_coupling', {}).get('coupling_strength', 0.5)
            theta_used = np.clip(self.base_theta + alpha * env_theta * np.pi, 0, np.pi)
        else:
            theta_used = self.base_theta
        
        return {
            'agent_id': self.agent_id,
            'counts': counts,
            'probability': p_hat,
            'std_error': std_error,
            'shots': shots,
            'circuit_params': {
                'base_theta': self.base_theta,
                'base_phi': self.base_phi,
                'theta_used': theta_used,
                'phi_used': self.base_phi,
                'env_theta': env_theta
            }
        }
    
    def get_agent_info(self) -> Dict:
        """Return agent metadata."""
        return {
            'agent_id': self.agent_id,
            'base_theta': self.base_theta,
            'base_phi': self.base_phi,
            'type': 'quantum_single_qubit'
        }


def initialize_agents(N: int, config: dict) -> list[QuantumAgent]:
    """
    Create N agents with uniform angular spacing.
    
    Agent i has parameters:
    θᵢ = (i/N) * π
    φᵢ = (i/N) * 2π
    
    This creates symmetric distribution of biases across decision space.
    
    Args:
        N: Number of agents
        config: Agent configuration dict
        
    Returns:
        List of QuantumAgent instances
    """
    agents = []
    
    for i in range(N):
        # Uniform angular spacing
        base_theta = (i / N) * np.pi
        base_phi = (i / N) * 2 * np.pi
        
        agent = QuantumAgent(
            agent_id=i,
            base_theta=base_theta,
            base_phi=base_phi,
            config=config
        )
        
        agents.append(agent)
    
    return agents