from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import requests


def _clean(text: str, max_len: int = 500) -> str:
    line = " ".join((text or "").split())
    if len(line) <= max_len:
        return line
    return line[: max_len - 3].rstrip() + "..."


def fetch_web_context_serpapi(
    query: str, max_items: int = 3, timeout_s: int = 8
) -> tuple[List[Dict[str, str]], Optional[int]]:
    """Fetch web snippets using SerpAPI (primary).
    
    Returns (snippets, duration_ms).
    Falls back to empty list on error.
    """
    api_key = os.getenv("SERPAPI_KEY", "").strip()
    if not api_key or not query.strip():
        return [], None

    max_items = max(1, min(max_items, 8))
    start_time = time.time()
    
    params = {
        "api_key": api_key,
        "q": query,
        "gl": "us",
        "hl": "en",
        "num": max_items,
    }

    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=timeout_s)
        resp.raise_for_status()
        data: Dict[str, Any] = resp.json() or {}
    except Exception:
        duration_ms = int((time.time() - start_time) * 1000)
        return [], duration_ms

    snippets: List[Dict[str, str]] = []
    
    # Extract organic search results
    if isinstance(data.get("organic_results"), list):
        for item in data["organic_results"]:
            if len(snippets) >= max_items:
                break
            if not isinstance(item, dict):
                continue
            
            title = _clean(str(item.get("title") or ""), max_len=150)
            snippet = _clean(str(item.get("snippet") or ""), max_len=500)
            url = str(item.get("link") or "")
            
            if title and snippet:
                snippets.append({
                    "title": title,
                    "snippet": snippet,
                    "url": url,
                    "source": "SerpAPI",
                })
    
    duration_ms = int((time.time() - start_time) * 1000)
    return snippets, duration_ms


def fetch_web_context_duckduckgo(query: str, max_items: int = 3, timeout_s: int = 8) -> tuple[List[Dict[str, str]], Optional[int]]:
    """Fallback: Fetch web snippets using DuckDuckGo (free).
    
    Returns (snippets, duration_ms).
    """
    if not query.strip():
        return [], None

    max_items = max(1, min(max_items, 8))
    start_time = time.time()
    
    params = {
        "q": query,
        "format": "json",
        "no_html": 1,
        "no_redirect": 1,
    }

    try:
        resp = requests.get("https://api.duckduckgo.com/", params=params, timeout=timeout_s)
        resp.raise_for_status()
        data: Dict[str, Any] = resp.json() or {}
    except Exception:
        duration_ms = int((time.time() - start_time) * 1000)
        return [], duration_ms

    snippets: List[Dict[str, str]] = []

    abstract = _clean(str(data.get("AbstractText") or ""))
    abstract_url = str(data.get("AbstractURL") or "")
    if abstract:
        snippets.append(
            {
                "title": _clean(str(data.get("Heading") or "DuckDuckGo"), max_len=120),
                "snippet": abstract,
                "url": abstract_url,
                "source": "DuckDuckGo",
            }
        )

    related = data.get("RelatedTopics")
    if isinstance(related, list):
        for item in related:
            if len(snippets) >= max_items:
                break
            if not isinstance(item, dict):
                continue

            if isinstance(item.get("Topics"), list):
                for nested in item["Topics"]:
                    if len(snippets) >= max_items:
                        break
                    if not isinstance(nested, dict):
                        continue
                    text = _clean(str(nested.get("Text") or ""))
                    url = str(nested.get("FirstURL") or "")
                    if text:
                        snippets.append({"title": "Related", "snippet": text, "url": url, "source": "DuckDuckGo"})
                continue

            text = _clean(str(item.get("Text") or ""))
            url = str(item.get("FirstURL") or "")
            if text:
                snippets.append({"title": "Related", "snippet": text, "url": url, "source": "DuckDuckGo"})

    duration_ms = int((time.time() - start_time) * 1000)
    return snippets[:max_items], duration_ms


def fetch_web_context(query: str, max_items: int = 3, timeout_s: int = 8) -> List[Dict[str, str]]:
    """Fetch web context snippets.
    
    Tries SerpAPI first (if key available), falls back to DuckDuckGo.
    Returns list of dicts with title, snippet, url, source.
    """
    # Try SerpAPI first
    snippets, _ = fetch_web_context_serpapi(query, max_items, timeout_s)
    if snippets:
        return snippets
    
    # Fallback to DuckDuckGo
    snippets, _ = fetch_web_context_duckduckgo(query, max_items, timeout_s)
    return snippets

