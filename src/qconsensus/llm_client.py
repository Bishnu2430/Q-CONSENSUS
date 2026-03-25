from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List, Optional

import requests


class LlamaCppClient:
    """Minimal client for a llama.cpp server with OpenAI-compatible endpoints."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, mock_mode: bool = False):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or "http://localhost:8080").rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.mock_mode = mock_mode or os.getenv("MOCK_LLM") == "true"

    def chat(self, *, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 512) -> str:
        if self.mock_mode:
            return self._mock_response(messages, temperature)
        
        try:
            url = f"{self.base_url}/v1/chat/completions"
            headers: Dict[str, str] = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            payload: Dict[str, Any] = {
                "model": "local-model",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=300)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (requests.RequestException, ConnectionError) as e:
            # Fallback to mock if server is unavailable
            print(f"Warning: LLM server unavailable ({e}), using mock responses")
            return self._mock_response(messages, temperature)

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
        
        return responses[seed % len(responses)]
