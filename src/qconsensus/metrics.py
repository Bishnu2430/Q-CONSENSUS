"""Chain verification and metrics for Q-CONSENSUS."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from web3 import Web3

from .contract_anchor import ContractAnchoringClient
from .events import JsonlEventStore


class ChainVerifier:
    """Verifies that run commitments are anchored on-chain."""

    def __init__(self, *, anchor_client: Optional[ContractAnchoringClient] = None, event_store: Optional[JsonlEventStore] = None):
        self.anchor_client = anchor_client
        self.event_store = event_store

    def verify_run(self, *, run_id: str, contract_address: Optional[str] = None) -> Dict[str, Any]:
        """Verify a run's commitment on-chain."""
        if not self.anchor_client:
            return {"verified": False, "reason": "No anchor client configured"}

        if not contract_address:
            return {"verified": False, "reason": "No contract address provided"}

        # Get commitment from event store
        if self.event_store:
            events = list(self.event_store.iter_events(run_id))
            commitment = None
            for ev in events:
                if ev.event_type == "run_committed":
                    commitment = ev.payload.get("commitment")
                    break

            if not commitment:
                return {"verified": False, "reason": "No commitment found in event log"}
        else:
            return {"verified": False, "reason": "No event store configured"}

        # Verify on-chain
        on_chain_commitment = self.anchor_client.verify_commitment(run_id=run_id, contract_address=contract_address)

        if on_chain_commitment is None:
            return {"verified": False, "reason": "Commitment not found on-chain", "expected": commitment}

        # Normalize for comparison
        expected = commitment.lower().lstrip("0x")
        actual = on_chain_commitment.lower().lstrip("0x")

        if expected == actual or expected == actual[-64:]:
            return {"verified": True, "on_chain_commitment": on_chain_commitment, "event_commitment": commitment}

        return {"verified": False, "reason": "On-chain commitment mismatch", "expected": commitment, "actual": on_chain_commitment}


class MetricsCollector:
    """Collects and aggregates metrics for debate runs."""

    def __init__(self):
        self.runs: Dict[str, Dict[str, Any]] = {}

    def record_run(
        self,
        *,
        run_id: str,
        quantum_policy: Dict[str, bool],
        num_agents: int,
        num_rounds: int,
        total_messages: int,
    ) -> None:
        """Record metrics for a completed run."""
        self.runs[run_id] = {
            "quantum_policy": quantum_policy,
            "num_agents": num_agents,
            "num_rounds": num_rounds,
            "total_messages": total_messages,
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics across all runs."""
        if not self.runs:
            return {"total_runs": 0}

        total_runs = len(self.runs)
        quantum_enabled = sum(1 for r in self.runs.values() if r.get("quantum_policy", {}).get("use_quantum_weights"))
        avg_agents = sum(r.get("num_agents", 0) for r in self.runs.values()) / total_runs
        avg_rounds = sum(r.get("num_rounds", 0) for r in self.runs.values()) / total_runs
        total_messages = sum(r.get("total_messages", 0) for r in self.runs.values())

        return {
            "total_runs": total_runs,
            "quantum_enabled_count": quantum_enabled,
            "quantum_pct": (quantum_enabled / total_runs * 100) if total_runs > 0 else 0,
            "avg_agents": avg_agents,
            "avg_rounds": avg_rounds,
            "total_messages": total_messages,
        }

    def get_quantum_vs_classical(self) -> Dict[str, List[str]]:
        """Get breakdown of runs by quantum policy selection."""
        quantum_runs = []
        classical_runs = []

        for run_id, metrics in self.runs.items():
            if metrics.get("quantum_policy", {}).get("use_quantum_weights"):
                quantum_runs.append(run_id)
            else:
                classical_runs.append(run_id)

        return {"quantum": quantum_runs, "classical": classical_runs}
