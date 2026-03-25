from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests


class LlamaCppClient:
    """Minimal client for a llama.cpp server with OpenAI-compatible endpoints."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or "http://localhost:8080").rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY")

    def chat(self, *, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 512) -> str:
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
