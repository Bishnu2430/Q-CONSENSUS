from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class LLMUnavailableError(RuntimeError):
    """The LLM server could not produce a completion (unreachable, timed out, or errored)."""


class LlamaCppClient:
    """Minimal client for a llama.cpp server with OpenAI-compatible endpoints."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, mock_mode: bool = False):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or "http://localhost:8080").rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.mock_mode = mock_mode or os.getenv("MOCK_LLM") == "true"
        # Prompts in debate_policy.py ask for <=200-word replies (~270 tokens);
        # the budget leaves headroom so a reply isn't cut off mid-sentence.
        self.default_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "400"))
        self.request_timeout_s = int(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "180"))

    def chat(self, *, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: Optional[int] = None) -> str:
        if self.mock_mode:
            return self._mock_response(messages, temperature)

        url = f"{self.base_url}/v1/chat/completions"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: Dict[str, Any] = {
            "model": "local-model",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.default_max_tokens,
        }
        # No silent fallback to canned text: a mock reply here would be
        # presented to the user as the debate's real final answer. Fail the
        # run with a clear reason instead; mocks are opt-in via MOCK_LLM=true.
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.request_timeout_s)
            resp.raise_for_status()
            choice = resp.json()["choices"][0]
        except (requests.RequestException, ValueError, KeyError, IndexError) as e:
            raise LLMUnavailableError(
                f"LLM server at {self.base_url} failed: {e}. "
                "Start it (docker compose up -d llama) or set MOCK_LLM=true for offline testing."
            ) from e

        if choice.get("finish_reason") == "length":
            logger.warning(
                "[LLM] completion hit max_tokens=%s and was truncated; raise LLM_MAX_TOKENS if this recurs",
                payload["max_tokens"],
            )
        return choice["message"]["content"]

    def _mock_response(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        """Generate deterministic mock responses based on message content."""
        content = " ".join(m.get("content", "") for m in messages)
        hash_val = int(hashlib.md5(content.encode()).hexdigest(), 16)
        seed = hash_val % 1000

        responses = [
            f"Mock response (seed={seed}): The evidence suggests a balanced analysis is warranted. Based on the given context, a moderate position appears most reasonable.",
            f"This perspective has merit. The key consideration is that both viewpoints contain valid points that should be integrated into a nuanced conclusion.",
            f"After careful consideration, the most defensible position accounts for the complexity indicated by multiple factors. Agreement on fundamentals while allowing for interpretation seems optimal.",
            f"The analysis reveals that reasonable experts could differ on specifics while agreeing on core principles. A synthesis approach that honors both perspectives is preferable.",
            f"Additional scrutiny suggests the initial assessment warrants qualification. When examined closely, the evidence points toward a more refined understanding that encompasses prior concerns.",
        ]

        # Labelled so canned text can never be mistaken for a real answer in the UI.
        return "[MOCK LLM] " + responses[seed % len(responses)]
