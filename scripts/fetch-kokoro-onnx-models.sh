#!/usr/bin/env bash
# Populate a host/volume cache with Kokoro ONNX q8/int8 weights (~115 MB total).
# Not run during Docker build — mount the directory at CINEMATH_TTS_MODEL_DIR.
set -euo pipefail

TARGET="${1:-${CINEMATH_TTS_MODEL_DIR:-/var/lib/cinemath/tts}}"
BASE_URL="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"

mkdir -p "$TARGET"

fetch() {
  local name="$1"
  local dest="$TARGET/$name"
  if [[ -f "$dest" && -s "$dest" ]]; then
    echo "skip (exists): $dest"
    return 0
  fi
  echo "fetch: $name -> $dest"
  curl -fsSL --retry 3 -o "$dest" "$BASE_URL/$name"
}

fetch "kokoro-v1.0.int8.onnx"
fetch "voices-v1.0.bin"

echo "Kokoro ONNX assets ready under $TARGET"
du -sh "$TARGET"
