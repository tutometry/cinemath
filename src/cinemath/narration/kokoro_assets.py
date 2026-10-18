"""Kokoro ONNX asset paths (mounted volume — not baked into images)."""

from __future__ import annotations

import os
from pathlib import Path

from cinemath.narration.config import model_dir

# Architect default: int8/q8 (~88–92 MB), not fp32 (~310 MB).
DEFAULT_ONNX_NAME = "kokoro-v1.0.int8.onnx"
DEFAULT_VOICES_NAME = "voices-v1.0.bin"

_ENV_ONNX = "CINEMATH_KOKORO_ONNX"
_ENV_VOICES = "CINEMATH_KOKORO_VOICES"


def kokoro_onnx_path() -> Path:
    override = (os.environ.get(_ENV_ONNX) or "").strip()
    if override:
        return Path(override).expanduser()
    return Path(model_dir()) / DEFAULT_ONNX_NAME


def kokoro_voices_path() -> Path:
    override = (os.environ.get(_ENV_VOICES) or "").strip()
    if override:
        return Path(override).expanduser()
    return Path(model_dir()) / DEFAULT_VOICES_NAME


def kokoro_assets_ready() -> bool:
    onnx = kokoro_onnx_path()
    voices = kokoro_voices_path()
    if not onnx.is_file() or not voices.is_file():
        return False
    return onnx.stat().st_size > 0 and voices.stat().st_size > 0


def ensure_model_dir() -> Path:
    root = Path(model_dir())
    root.mkdir(parents=True, exist_ok=True)
    return root
