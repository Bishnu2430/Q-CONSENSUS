import os

from fastapi.testclient import TestClient

from src.qconsensus.security import InMemoryRateLimiter
from src.qconsensus.web import create_app


def _set_test_env(tmp_path, **overrides):
    os.environ["EVENT_STORE_DIR"] = str(tmp_path / "events")
    os.environ["MOCK_LLM"] = "true"
    os.environ["CONTRACT_ANCHOR_ENABLED"] = "false"
    os.environ["AGENTS_CONFIG_PATH"] = "config/agents.yaml"
    os.environ.pop("API_KEY", None)
    os.environ.pop("RUN_RATE_LIMIT_MAX", None)
    os.environ.pop("RUN_RATE_LIMIT_WINDOW_SECONDS", None)
    for key, value in overrides.items():
        os.environ[key] = value


def test_rate_limiter_allows_up_to_max_then_blocks():
    limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-a") is False


def test_rate_limiter_tracks_keys_independently():
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-b") is True
    assert limiter.allow("client-a") is False
    assert limiter.allow("client-b") is False


def test_status_endpoint_is_open_without_api_key(tmp_path):
    _set_test_env(tmp_path)
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/status")
    assert resp.status_code == 200


def test_run_endpoint_rejects_missing_api_key_when_configured(tmp_path):
    _set_test_env(tmp_path, API_KEY="secret123")
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/run", json={"query": "test query"})
    assert resp.status_code == 401


def test_run_endpoint_accepts_correct_api_key(tmp_path):
    _set_test_env(tmp_path, API_KEY="secret123")
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/run", json={"query": "test query"}, headers={"X-API-Key": "secret123"})
    assert resp.status_code == 200


def test_run_endpoint_rate_limited_after_threshold(tmp_path):
    _set_test_env(tmp_path, RUN_RATE_LIMIT_MAX="2", RUN_RATE_LIMIT_WINDOW_SECONDS="60")
    app = create_app()
    client = TestClient(app)

    r1 = client.post("/api/run", json={"query": "q1"})
    r2 = client.post("/api/run", json={"query": "q2"})
    r3 = client.post("/api/run", json={"query": "q3"})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
