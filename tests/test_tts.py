import os

import pytest
from fastapi.testclient import TestClient

from src.qconsensus.tts import TTSEngine
from src.qconsensus.web import create_app

_VOICE_MODEL_PATH = os.path.join("models", "tts", "en_US-libritts_r-medium.onnx")
_voice_model_available = pytest.mark.skipif(
    not os.path.exists(_VOICE_MODEL_PATH),
    reason="Piper voice model not downloaded (run scripts/download_tts_voice.py)",
)


def _set_test_env(tmp_path, **overrides):
    os.environ["EVENT_STORE_DIR"] = str(tmp_path / "events")
    os.environ["MOCK_LLM"] = "true"
    os.environ["CONTRACT_ANCHOR_ENABLED"] = "false"
    os.environ["AGENTS_CONFIG_PATH"] = "config/agents.yaml"
    os.environ.pop("API_KEY", None)
    os.environ.pop("TTS_ENABLED", None)
    os.environ.pop("TTS_VOICE_MODEL_PATH", None)
    for key, value in overrides.items():
        os.environ[key] = value


def test_from_env_disabled_by_default(tmp_path):
    os.environ.pop("TTS_ENABLED", None)
    assert TTSEngine.from_env() is None


def test_from_env_disabled_when_model_missing(tmp_path):
    os.environ["TTS_ENABLED"] = "true"
    os.environ["TTS_VOICE_MODEL_PATH"] = str(tmp_path / "does-not-exist.onnx")
    assert TTSEngine.from_env() is None
    os.environ.pop("TTS_ENABLED", None)
    os.environ.pop("TTS_VOICE_MODEL_PATH", None)


@_voice_model_available
def test_speaker_id_for_agent_is_deterministic_and_in_range():
    engine = TTSEngine(model_path=_VOICE_MODEL_PATH)
    sid_a = engine.speaker_id_for_agent("proposer")
    sid_b = engine.speaker_id_for_agent("proposer")
    sid_c = engine.speaker_id_for_agent("skeptic")

    assert sid_a == sid_b
    assert 0 <= sid_a < engine.num_speakers
    assert 0 <= sid_c < engine.num_speakers


@_voice_model_available
def test_synthesize_wav_returns_valid_wav_bytes():
    engine = TTSEngine(model_path=_VOICE_MODEL_PATH)
    wav_bytes = engine.synthesize_wav(text="This is a test.", agent_id="proposer")

    assert wav_bytes[:4] == b"RIFF"
    assert len(wav_bytes) > 100


@_voice_model_available
def test_tts_endpoint_returns_wav_when_enabled(tmp_path):
    _set_test_env(tmp_path, TTS_ENABLED="true", TTS_VOICE_MODEL_PATH=_VOICE_MODEL_PATH)
    app = create_app()
    client = TestClient(app)

    resp = client.post("/api/tts", json={"agent_id": "proposer", "text": "hello there"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert resp.content[:4] == b"RIFF"


def test_tts_endpoint_returns_503_when_disabled(tmp_path):
    _set_test_env(tmp_path)
    app = create_app()
    client = TestClient(app)

    resp = client.post("/api/tts", json={"agent_id": "proposer", "text": "hello"})
    assert resp.status_code == 503


def test_status_reports_tts_enabled_flag(tmp_path):
    _set_test_env(tmp_path)
    app = create_app()
    client = TestClient(app)

    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json()["tts_enabled"] is False
