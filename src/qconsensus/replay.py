"""Replay tool for deterministic re-execution of debate runs."""

from __future__ import annotations

from typing import List, Optional

from .events import Event, JsonlEventStore
from .llm_client import LlamaCppClient
from .types import DebateMessage


class ReplayConfig:
    """Configuration for replaying a run."""

    def __init__(self, *, skip_llm: bool = True, mock_responses: Optional[dict] = None):
        self.skip_llm = skip_llm
        self.mock_responses = mock_responses or {}


class DebateReplayer:
    """Replays a debate run from stored events."""

    def __init__(self, *, event_store: JsonlEventStore, llm: Optional[LlamaCppClient] = None):
        self.event_store = event_store
        self.llm = llm

    def replay(self, *, run_id: str, config: Optional[ReplayConfig] = None) -> dict:
        """Replay a run from its event log."""
        config = config or ReplayConfig()

        events = list(self.event_store.iter_events(run_id))
        if not events:
            raise ValueError(f"No events found for run_id: {run_id}")

        replay_result = {
            "run_id": run_id,
            "events_count": len(events),
            "messages": [],
            "agent_responses": {},
            "quantum_decisions": {},
            "consensus": None,
            "final_answer": None,
        }

        for ev in events:
            if ev.event_type == "agent_responded":
                agent_id = ev.payload.get("agent_id", "unknown")
                content = ev.payload.get("content", "")
                round_idx = ev.payload.get("round_idx", 0)

                msg = {
                    "agent_id": agent_id,
                    "round": round_idx,
                    "content": content,
                }
                replay_result["messages"].append(msg)

                if round_idx == 0:
                    if agent_id not in replay_result["agent_responses"]:
                        replay_result["agent_responses"][agent_id] = {}
                    replay_result["agent_responses"][agent_id]["initial"] = content

            elif ev.event_type == "quantum_randomness":
                payload = ev.payload
                replay_result["quantum_decisions"]["randomness"] = {
                    "quantum_order": payload.get("quantum_order"),
                    "classical_order": payload.get("classical_order"),
                    "selected_order": payload.get("selected_order"),
                    "selected_policy": payload.get("selected_policy"),
                }

            elif ev.event_type == "quantum_scheduling":
                payload = ev.payload
                replay_result["quantum_decisions"]["scheduling"] = {
                    "quantum_scores": payload.get("quantum_scores"),
                    "classical_scores": payload.get("classical_scores"),
                    "selected_policy": payload.get("selected_policy"),
                }

            elif ev.event_type == "consensus_weights":
                payload = ev.payload
                replay_result["consensus"] = {
                    "angles": payload.get("angles"),
                    "quantum_weights": payload.get("quantum_weights"),
                    "classical_weights": payload.get("classical_weights"),
                    "selected_weights": payload.get("selected_weights"),
                    "selected_policy": payload.get("selected_policy"),
                }

            elif ev.event_type == "final_answer":
                payload = ev.payload
                replay_result["final_answer"] = payload.get("final_answer")
                replay_result["quantum_baseline"] = payload.get("quantum_baseline_answer")
                replay_result["classical_baseline"] = payload.get("classical_baseline_answer")
                replay_result["selected_policy"] = payload.get("selected_policy")

        return replay_result
