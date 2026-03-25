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


def build_cross_critique_prompt(
    *,
    user_query: str,
    agent: AgentSpec,
    own_answer: str,
    peer_answers: Dict[str, str],
) -> List[dict]:
    peer_lines = []
    for peer_id, ans in peer_answers.items():
        peer_lines.append(f"Peer {peer_id} answer:\n{ans}")
    peers_text = "\n\n".join(peer_lines)

    return [
        {"role": "system", "content": agent.system_prompt.strip()},
        {
            "role": "user",
            "content": (
                "Cross-critique round.\n\n"
                "Task:\n"
                "- Critique peers for logic gaps, missing checks, and unsupported claims.\n"
                "- Keep critique concise and actionable.\n"
                "- End with a bullet list of highest-risk failure modes.\n"
                "- Do NOT reveal hidden chain-of-thought; only provide rationale summary.\n\n"
                f"User query:\n{user_query}\n\n"
                f"Your prior answer:\n{own_answer}\n\n"
                f"Peer answers:\n\n{peers_text}"
            ),
        },
    ]


def build_self_revision_prompt(
    *,
    user_query: str,
    agent: AgentSpec,
    own_answer: str,
    critiques_from_peers: Dict[str, str],
) -> List[dict]:
    critique_lines = []
    for peer_id, critique in critiques_from_peers.items():
        critique_lines.append(f"Peer {peer_id} critique:\n{critique}")
    critiques_text = "\n\n".join(critique_lines)

    return [
        {"role": "system", "content": agent.system_prompt.strip()},
        {
            "role": "user",
            "content": (
                "Self-revision round.\n\n"
                "Task:\n"
                "- Revise your answer using peer critiques.\n"
                "- Include a short change-log of what you corrected.\n"
                "- Include final confidence (low/medium/high) with one-line reason.\n"
                "- Do NOT reveal hidden chain-of-thought; only provide rationale summary.\n\n"
                f"User query:\n{user_query}\n\n"
                f"Your prior answer:\n{own_answer}\n\n"
                f"Peer critiques:\n\n{critiques_text}"
            ),
        },
    ]
