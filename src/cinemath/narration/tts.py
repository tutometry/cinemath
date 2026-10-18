"""Synthesize WAV clips (Kokoro-82M on CPU, Piper fallback)."""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

from cinemath.core.logger import get_logger
from cinemath.narration.config import kokoro_voice, piper_model_path, tts_engine, tts_mock
from cinemath.narration.kokoro_assets import (
    ensure_model_dir,
    kokoro_assets_ready,
    kokoro_onnx_path,
    kokoro_voices_path,
)
from cinemath.narration.plain_text import narration_to_speech

log = get_logger("narration.tts")

_SAMPLE_RATE = 24_000
_kokoro_engine = None


class TtsError(RuntimeError):
    pass


def synthesize_line(text: str, dest: Path) -> Path:
    """Write a mono 24 kHz WAV for one narration line."""
    spoken = narration_to_speech(text)
    if not spoken:
        return _write_silence(dest, duration_s=0.15)

    dest.parent.mkdir(parents=True, exist_ok=True)
    engine = tts_engine()
    if tts_mock() or engine == "mock":
        log.warning(
            "CINEMATH_TTS_MOCK=1 (or engine=mock): using placeholder beep audio — "
            "unset mock and install Kokoro weights for real speech"
        )
        return _write_mock_tone(dest, spoken)

    if engine in {"auto", "kokoro"}:
        try:
            return _synthesize_kokoro(spoken, dest)
        except TtsError as exc:
            log.warning("Kokoro TTS failed (%s); trying Piper fallback", exc)
            if engine == "kokoro":
                raise

    try:
        return _synthesize_piper(spoken, dest)
    except TtsError as exc:
        if _say_available():
            log.warning("Piper TTS failed (%s); using macOS say", exc)
            return _synthesize_say(spoken, dest)
        raise TtsError(f"All TTS backends failed: {exc}") from exc


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate() or _SAMPLE_RATE
        return handle.getnframes() / float(rate)


def _say_available() -> bool:
    return shutil.which("say") is not None and shutil.which("ffmpeg") is not None


def _synthesize_say(text: str, dest: Path) -> Path:
    """System voice on macOS when Kokoro weights are not installed."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    aiff = dest.with_suffix(".aiff")
    say = subprocess.run(
        ["say", "-o", str(aiff), text],
        check=False,
        capture_output=True,
        text=True,
    )
    if say.returncode != 0:
        raise TtsError(say.stderr.strip() or "say failed")
    ffmpeg = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(aiff),
            "-ac",
            "1",
            "-ar",
            str(_SAMPLE_RATE),
            str(dest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    aiff.unlink(missing_ok=True)
    if ffmpeg.returncode != 0 or not dest.is_file():
        raise TtsError(ffmpeg.stderr.strip() or "ffmpeg failed to convert say audio")
    return dest


def _synthesize_kokoro(text: str, dest: Path) -> Path:
    try:
        import soundfile as sf  # type: ignore[import-not-found]
    except ImportError as exc:
        raise TtsError("kokoro-onnx optional dependencies are not installed") from exc

    ensure_model_dir()
    if not kokoro_assets_ready():
        raise TtsError(
            "Kokoro ONNX assets missing — run scripts/fetch-kokoro-onnx-models.sh "
            f"into {kokoro_onnx_path().parent}"
        )

    voice = kokoro_voice()
    try:
        engine = _kokoro()
    except ImportError as exc:
        raise TtsError("kokoro-onnx optional dependencies are not installed") from exc
    samples, sample_rate = engine.create(text, voice=voice, speed=1.0, lang="en-us")
    if samples is None or len(samples) == 0:
        raise TtsError("Kokoro ONNX returned no audio")
    sf.write(str(dest), samples, int(sample_rate))
    return dest


def _kokoro():
    """Load the ONNX voice once per process."""
    global _kokoro_engine
    if _kokoro_engine is None:
        from kokoro_onnx import Kokoro  # type: ignore[import-not-found]

        _kokoro_engine = Kokoro(str(kokoro_onnx_path()), str(kokoro_voices_path()))
    return _kokoro_engine


def _synthesize_piper(text: str, dest: Path) -> Path:
    model = piper_model_path()
    if not model:
        raise TtsError("CINEMATH_PIPER_MODEL is not set for Piper fallback")

    model_path = Path(model)
    if not model_path.is_file():
        raise TtsError(f"Piper model not found: {model_path}")

    try:
        from piper import PiperVoice  # type: ignore[import-not-found]
    except ImportError as exc:
        raise TtsError("piper-tts is not installed") from exc

    voice = PiperVoice.load(str(model_path))
    with wave.open(str(dest), "wb") as handle:
        voice.synthesize(text, handle)
    return dest


def _write_silence(dest: Path, *, duration_s: float) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    n_frames = int(_SAMPLE_RATE * max(duration_s, 0.05))
    with wave.open(str(dest), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(_SAMPLE_RATE)
        handle.writeframes(b"\x00\x00" * n_frames)
    return dest


def _write_mock_tone(dest: Path, text: str) -> Path:
    """Deterministic placeholder audio for CI / dev without model weights."""
    duration_s = min(6.0, 0.35 + 0.055 * len(text))
    dest.parent.mkdir(parents=True, exist_ok=True)
    n_frames = int(_SAMPLE_RATE * duration_s)
    freq = 220.0
    with wave.open(str(dest), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(_SAMPLE_RATE)
        frames = bytearray()
        for i in range(n_frames):
            sample = int(8000 * math.sin(2 * math.pi * freq * (i / _SAMPLE_RATE)))
            frames.extend(struct.pack("<h", sample))
        handle.writeframes(frames)
    return dest
