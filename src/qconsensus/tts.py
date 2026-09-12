"""Local text-to-speech for agent responses.

Uses Piper (https://github.com/OHF-Voice/piper1-gpl), a small ONNX-based
local TTS engine with no GPU/PyTorch dependency and no external network
calls at synthesis time -- consistent with the rest of this project's
"works fully offline" design (the LLM client's mock fallback, the
blockchain anchor's optional startup).

Rather than downloading one full voice model per agent persona (each is
tens of MB), this uses a single multi-speaker model
(en_US-libritts_r-medium, ~900 built-in speakers) and assigns each agent a
distinct speaker deterministically by hashing its agent_id. Same agent,
same voice, every run -- and no extra assets beyond the one model file.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import wave
from typing import Optional

logger = logging.getLogger(__name__)


class TTSEngine:
    """Wraps a loaded Piper voice model for on-demand synthesis."""

    def __init__(self, *, model_path: str):
        from piper import PiperVoice  # imported lazily so piper stays optional

        self.model_path = model_path
        self.voice = PiperVoice.load(model_path)
        self.num_speakers = self.voice.config.num_speakers or 1

    @staticmethod
    def from_env() -> Optional["TTSEngine"]:
        enabled = os.getenv("TTS_ENABLED", "false").lower() in {"1", "true", "yes"}
        if not enabled:
            return None

        model_path = os.getenv("TTS_VOICE_MODEL_PATH", os.path.join("models", "tts", "en_US-libritts_r-medium.onnx"))
        if not os.path.exists(model_path):
            logger.warning(
                "[TTS] TTS_ENABLED=true but voice model not found at %s -- "
                "run scripts/download_tts_voice.py first. TTS disabled.",
                model_path,
            )
            return None

        try:
            return TTSEngine(model_path=model_path)
        except Exception:
            logger.exception("[TTS] failed to load voice model at %s -- TTS disabled", model_path)
            return None

    def speaker_id_for_agent(self, agent_id: str) -> int:
        """Deterministically map an agent_id to one of the model's speakers."""
        digest = hashlib.sha256(agent_id.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % self.num_speakers

    def synthesize_wav(self, *, text: str, agent_id: str) -> bytes:
        """Synthesize `text` in the voice assigned to `agent_id`, as WAV bytes."""
        from piper import SynthesisConfig

        speaker_id = self.speaker_id_for_agent(agent_id)
        syn_config = SynthesisConfig(speaker_id=speaker_id) if self.num_speakers > 1 else None

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            self.voice.synthesize_wav(text, wf, syn_config=syn_config)
        return buf.getvalue()
