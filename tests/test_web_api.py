import os
import time

from fastapi.testclient import TestClient

from src.qconsensus.web import create_app


def _set_test_env(tmp_path):
    os.environ["EVENT_STORE_DIR"] = str(tmp_path / "events")
    os.environ["MOCK_LLM"] = "true"
    os.environ["CONTRACT_ANCHOR_ENABLED"] = "false"
    os.environ["AGENTS_CONFIG_PATH"] = "config/agents.yaml"


def test_sync_run_and_events(tmp_path):
    _set_test_env(tmp_path)
    app = create_app()
    client = TestClient(app)

    payload = {
        "query": "Summarize tradeoffs.",
        "max_rounds": 3,
        "use_quantum_randomness": True,
        "use_quantum_weights": False,
        "use_quantum_scheduling": True,
    }
    resp = client.post("/api/run", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    assert body["run_id"]
    assert body["commitment"]
    assert body["final_answer"]

    ev = client.get(f"/api/events/{body['run_id']}")
    assert ev.status_code == 200
    assert len(ev.json()) > 0


def test_async_run_and_result(tmp_path):
    _set_test_env(tmp_path)
    app = create_app()
    client = TestClient(app)

    payload = {
        "query": "Design a deployment checklist.",
        "max_rounds": 2,
        "use_quantum_randomness": True,
        "use_quantum_weights": True,
        "use_quantum_scheduling": False,
    }

    started = client.post("/api/run_async", json=payload)
    assert started.status_code == 200
    run_id = started.json()["run_id"]

    deadline = time.time() + 15
    result = None
    while time.time() < deadline:
        rr = client.get(f"/api/result/{run_id}")
        assert rr.status_code == 200
        result = rr.json()
        if result["status"] in {"completed", "failed"}:
            break
        time.sleep(0.2)

    assert result is not None
    assert result["status"] == "completed"
    assert result["commitment"]
