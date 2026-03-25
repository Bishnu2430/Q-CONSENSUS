from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    display_name: str
    system_prompt: str


@dataclass(frozen=True)
class DebateConfig:
    agents: List[AgentSpec]
    max_rounds: int = 2


@dataclass(frozen=True)
class DebateMessage:
    run_id: str
    agent_id: str
    role: str
    content: str
    round_idx: int


@dataclass(frozen=True)
class DebateResult:
    run_id: str
    final_answer: str
    messages: List[DebateMessage]
    commitment: str
    anchor_tx_hash: Optional[str]
