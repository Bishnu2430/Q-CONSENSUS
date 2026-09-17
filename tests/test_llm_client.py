import json
import logging
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from src.qconsensus.debate_policy import (
    build_agent_prompts,
    build_cross_critique_prompt,
    build_self_revision_prompt,
)
from src.qconsensus.llm_client import LlamaCppClient, LLMUnavailableError
from src.qconsensus.types import AgentSpec


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _StubLlamaServer:
    """Tiny OpenAI-compatible stub that returns a canned completion."""

    def __init__(self, *, content: str, finish_reason: str):
        body = json.dumps(
            {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}
        ).encode()
        self.requests: list[dict] = []
        requests = self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                requests.append(json.loads(self.rfile.read(length)))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


def test_unreachable_llm_raises_instead_of_returning_canned_text(monkeypatch):
    monkeypatch.delenv("MOCK_LLM", raising=False)
    client = LlamaCppClient(base_url=f"http://127.0.0.1:{_closed_port()}")

    with pytest.raises(LLMUnavailableError) as exc_info:
        client.chat(messages=[{"role": "user", "content": "Should cities ban cars?"}])

    assert "MOCK_LLM" in str(exc_info.value)


def test_mock_mode_output_is_clearly_labelled():
    client = LlamaCppClient(mock_mode=True)

    reply = client.chat(messages=[{"role": "user", "content": "Should cities ban cars?"}])

    assert reply.startswith("[MOCK LLM]")


def test_default_token_budget_leaves_headroom(monkeypatch):
    monkeypatch.delenv("LLM_MAX_TOKENS", raising=False)
    stub = _StubLlamaServer(content="Answer: yes.", finish_reason="stop")
    try:
        LlamaCppClient(base_url=stub.url).chat(messages=[{"role": "user", "content": "q"}])
    finally:
        stub.close()

    assert stub.requests[0]["max_tokens"] >= 384


def test_truncated_completion_is_logged(caplog):
    stub = _StubLlamaServer(content="Pros:\n- cleaner air\n-", finish_reason="length")
    try:
        with caplog.at_level(logging.WARNING, logger="src.qconsensus.llm_client"):
            reply = LlamaCppClient(base_url=stub.url).chat(messages=[{"role": "user", "content": "q"}])
    finally:
        stub.close()

    assert reply == "Pros:\n- cleaner air\n-"
    assert any("max_tokens" in r.getMessage() for r in caplog.records)


AGENT = AgentSpec(agent_id="proposer", display_name="Proposer", system_prompt="You are the Proposer.")


def _user_turn(messages: list[dict]) -> str:
    return next(m["content"] for m in messages if m["role"] == "user")


def test_prompts_ask_for_a_direct_bounded_answer_to_the_query():
    query = "Should cities ban cars from downtown areas? Give pros, risks and a recommendation."

    initial = _user_turn(build_agent_prompts(user_query=query, agents=[AGENT])["proposer"])
    critique = _user_turn(
        build_cross_critique_prompt(user_query=query, agent=AGENT, own_answer="a", peer_answers={"skeptic": "b"})
    )
    revision = _user_turn(
        build_self_revision_prompt(user_query=query, agent=AGENT, own_answer="a", critiques_from_peers={"skeptic": "c"})
    )

    for prompt in (initial, critique, revision):
        assert query in prompt
        assert "words" in prompt  # every round states an explicit length budget

    # The rounds whose output can become the final answer must lead with the answer itself.
    for prompt in (initial, revision):
        assert "Answer:" in prompt
        assert "cover every part" in prompt
