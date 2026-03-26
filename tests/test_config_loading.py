import os

from src.qconsensus.web import _load_agents_from_yaml


def test_yaml_agent_loading(tmp_path):
    cfg = tmp_path / "agents.yaml"
    cfg.write_text(
        """
agents:
  - agent_id: alpha
    display_name: Alpha
    system_prompt: Alpha prompt
  - agent_id: beta
    display_name: Beta
    system_prompt: Beta prompt
""".strip()
        + "\n",
        encoding="utf-8",
    )

    agents = _load_agents_from_yaml(str(cfg))
    assert len(agents) == 2
    assert agents[0].agent_id == "alpha"
    assert agents[1].display_name == "Beta"


def test_yaml_loading_falls_back_to_defaults_when_missing(tmp_path):
    missing = tmp_path / "missing.yaml"
    agents = _load_agents_from_yaml(str(missing))
    assert len(agents) >= 3
