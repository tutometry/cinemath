"""Narration feature flags (default off until product ships)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_ENV_ENABLE = "CINEMATH_ENABLE_NARRATION"
_ENV_ENGINE = "CINEMATH_TTS_ENGINE"
_ENV_MOCK = "CINEMATH_TTS_MOCK"
_ENV_MODEL_DIR = "CINEMATH_TTS_MODEL_DIR"
_ENV_PIPER_MODEL = "CINEMATH_PIPER_MODEL"
_ENV_KOKORO_VOICE = "CINEMATH_KOKORO_VOICE"
_ENV_MUX_MODE = "CINEMATH_NARRATION_MUX"  # ffmpeg (default) | manim


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def narration_requested(
    *,
    option_flag: bool | None = None,
    options_payload: dict[str, Any] | None = None,
) -> bool:
    """True when narration should run for this job (explicit opt-in only)."""
    if option_flag is not None:
        return bool(option_flag)
    if options_payload:
        for key in ("enable_narration", "narration"):
            if key in options_payload:
                return bool(options_payload[key])
    return _truthy(os.environ.get(_ENV_ENABLE))


def tts_mock() -> bool:
    return _truthy(os.environ.get(_ENV_MOCK))


def tts_engine() -> str:
    """kokoro | piper | auto (try Kokoro, fall back to Piper)."""
    raw = (os.environ.get(_ENV_ENGINE) or "auto").strip().lower()
    if raw in {"kokoro", "piper", "auto", "mock"}:
        return raw
    return "auto"


def model_dir() -> str:
    """Where Kokoro ONNX weights live.

    ``CINEMATH_TTS_MODEL_DIR`` wins. Otherwise use the worker mount
    ``/var/lib/cinemath/tts`` when that directory exists, and a user cache
    for local installs.
    """
    override = (os.environ.get(_ENV_MODEL_DIR) or "").strip()
    if override:
        return override
    system = "/var/lib/cinemath/tts"
    if os.path.isdir(system):
        return system
    return str(Path.home() / ".cache" / "cinemath" / "tts")


def piper_model_path() -> str | None:
    path = (os.environ.get(_ENV_PIPER_MODEL) or "").strip()
    return path or None


def kokoro_voice() -> str:
    return (os.environ.get(_ENV_KOKORO_VOICE) or "af_heart").strip()


def mux_mode() -> str:
    raw = (os.environ.get(_ENV_MUX_MODE) or "ffmpeg").strip().lower()
    return raw if raw in {"ffmpeg", "manim"} else "ffmpeg"
