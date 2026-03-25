from __future__ import annotations

from typing import Dict, List

from .types import AgentSpec


def build_agent_prompts(*, user_query: str, agents: List[AgentSpec]) -> Dict[str, List[dict]]:
    """Build per-agent prompt messages.

    IMPORTANT: For observability and safety, we request structured *rationale summaries*,
    not hidden chain-of-thought.
    """
    prompts: Dict[str, List[dict]] = {}

    for agent in agents:
        system = agent.system_prompt.strip()
        prompts[agent.agent_id] = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "You are participating in a multi-agent debate.\n\n"
                    "Rules:\n"
                    "- Provide your best answer.\n"
                    "- Provide a concise rationale summary (bullet points).\n"
                    "- Provide a self-checklist of possible errors/unknowns.\n"
                    "- Do NOT reveal hidden chain-of-thought; only provide the summary rationale.\n\n"
                    f"User query:\n{user_query}"
                ),
            },
        ]

    return prompts
