"""Download the Piper voice model used for local TTS.

One-time setup step: fetches a single multi-speaker voice model (~75MB) into
models/tts/. Not committed to git (like the LLM model, this is a runtime
asset, but TTS is optional so it isn't force-bundled via LFS). Run this once,
then set TTS_ENABLED=true in .env.

Usage:
    python scripts/download_tts_voice.py [voice_name] [--download-dir DIR]
"""

import argparse
import sys
from pathlib import Path

from piper.download_voices import download_voice


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "voice",
        nargs="?",
        default="en_US-libritts_r-medium",
        help="Piper voice name (default: en_US-libritts_r-medium, a 904-speaker multi-voice model)",
    )
    parser.add_argument(
        "--download-dir",
        default="models/tts",
        help="Directory to download the voice model into (default: models/tts)",
    )
    args = parser.parse_args()

    download_dir = Path(args.download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading Piper voice '{args.voice}' into {download_dir}/ ...")
    download_voice(args.voice, download_dir)
    print(f"Done. Set TTS_ENABLED=true and TTS_VOICE_MODEL_PATH={download_dir / (args.voice + '.onnx')} in .env to use it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
