from src.qconsensus.debate import DebateOrchestrator
from src.qconsensus.events import JsonlEventStore
from src.qconsensus.llm_client import LlamaCppClient
from src.qconsensus.quantum_executor import QuantumExecutor
from src.qconsensus.types import AgentSpec, DebateConfig, QuantumPolicyConfig


def test_debate_runs_all_rounds(tmp_path):
    store = JsonlEventStore(str(tmp_path / "events"))
    llm = LlamaCppClient(mock_mode=True)
    qexec = QuantumExecutor({"base_seed": 42})

    orch = DebateOrchestrator(event_store=store, llm=llm, quantum_executor=qexec)

    agents = [
        AgentSpec(agent_id="a", display_name="A", system_prompt="Agent A"),
        AgentSpec(agent_id="b", display_name="B", system_prompt="Agent B"),
        AgentSpec(agent_id="c", display_name="C", system_prompt="Agent C"),
    ]

    cfg = DebateConfig(
        agents=agents,
        max_rounds=3,
        quantum=QuantumPolicyConfig(
            use_quantum_randomness=True,
            use_quantum_weights=True,
            use_quantum_scheduling=True,
        ),
    )

    result = orch.run(user_query="What is the best rollout strategy?", config=cfg)

    assert result.run_id
    assert result.commitment
    assert result.final_answer

    events = list(store.iter_events(result.run_id))
    event_types = [e.event_type for e in events]

    assert "quantum_randomness" in event_types
    assert "quantum_scheduling" in event_types
    assert "consensus_weights" in event_types
    assert "final_answer" in event_types
    assert "run_committed" in event_types

    rounds = sorted({m.round_idx for m in result.messages})
    assert rounds == [0, 1, 2]

    responses = [e for e in events if e.event_type == "agent_responded"]
    assert len(responses) == len(agents) * 3
