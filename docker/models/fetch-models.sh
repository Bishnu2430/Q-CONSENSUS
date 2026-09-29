#!/bin/sh
# Downloads the runtime model files into the "models" Docker volume (mounted
# at /models). Runs as the one-shot "models" service before llama starts and
# is a no-op once the files are present, so the GGUF model only ever lives in
# that volume -- never in the git repo or on the host.
#
# Environment (passed through from .env by docker-compose.yml):
#   LLAMA_MODEL_FILE      file name of the model inside the volume
#   LLAMA_MODEL_URL       where to download it from
#   LLAMA_MODEL_SHA256    expected sha256 (empty = skip verification)
#   TTS_ENABLED           when true, also fetch the Piper voice
#   TTS_VOICE_MODEL_PATH  models/tts/<voice>.onnx (relative to the app dir)
set -eu

MODELS_DIR=/models

is_true() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

fetch() {
  # fetch <url> <dest> [sha256]
  url="$1" dest="$2" sha="${3:-}"
  if [ -s "$dest" ]; then
    echo "present: ${dest#"$MODELS_DIR"/}"
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  part="$dest.part"
  echo "downloading ${dest#"$MODELS_DIR"/} from $url"
  [ -s "$part" ] && echo "resuming a previous partial download"
  # -C - resumes a .part file left behind by an interrupted earlier attempt.
  # The progress bar is shown even without a TTY: the launchers run this with
  # "docker compose run -T" (Git Bash can't give docker.exe a TTY).
  curl -fL --retry 5 --retry-delay 5 --retry-all-errors -C - --progress-bar -o "$part" "$url"
  if [ -n "$sha" ]; then
    echo "verifying sha256"
    actual="$(sha256sum "$part" | cut -d' ' -f1)"
    if [ "$actual" != "$sha" ]; then
      rm -f "$part"
      echo "checksum mismatch for $url: expected $sha, got $actual" >&2
      exit 1
    fi
  fi
  mv "$part" "$dest"
  echo "saved ${dest#"$MODELS_DIR"/}"
}

fetch "$LLAMA_MODEL_URL" "$MODELS_DIR/$LLAMA_MODEL_FILE" "${LLAMA_MODEL_SHA256:-}"

if is_true "${TTS_ENABLED:-false}"; then
  # Accept Windows-style separators and a leading ./ from .env.
  voice_path="$(printf '%s' "${TTS_VOICE_MODEL_PATH:-models/tts/en_US-libritts_r-medium.onnx}" | tr '\\' '/')"
  voice_path="${voice_path#./}"
  case "$voice_path" in
    models/*.onnx) ;;
    *)
      echo "TTS_VOICE_MODEL_PATH=$voice_path is not under models/; the container can't see it, skipping voice download" >&2
      exit 0
      ;;
  esac
  # Piper voice names are <lang>-<name>-<quality>, e.g. en_US-libritts_r-medium,
  # stored upstream as <family>/<lang>/<name>/<quality>/<voice>.onnx(.json).
  voice="$(basename "$voice_path" .onnx)"
  lang="${voice%%-*}"
  rest="${voice#*-}"
  quality="${rest##*-}"
  name="${rest%-*}"
  base="https://huggingface.co/rhasspy/piper-voices/resolve/main/${lang%%_*}/$lang/$name/$quality/$voice"
  dest="$MODELS_DIR/${voice_path#models/}"
  fetch "$base.onnx" "$dest"
  fetch "$base.onnx.json" "$dest.json"
fi
