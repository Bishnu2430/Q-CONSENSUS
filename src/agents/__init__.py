"""
Quantum agent layer for Q-CONSENSUS.

Provides quantum decision-making agents with parameterized circuits.
"""

from .quantum_agent import QuantumAgent, initialize_agents
from .circuit_builder import CircuitBuilder
from .quantum_executor import QuantumExecutor

__all__ = [
    'QuantumAgent',
    'initialize_agents',
    'CircuitBuilder',
    'QuantumExecutor'
]