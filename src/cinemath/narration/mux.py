"""Combine narration clips with rendered video (ffmpeg)."""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

from cinemath.core.logger import get_logger
from cinemath.narration.timeline import SpeechEvent
from cinemath.render_engine.video_color import tag_mp4_bt709_limited_range

log = get_logger("narration.mux")

_SAMPLE_RATE = 24_000


def mux_narration(
    video_path: Path,
    events: list[SpeechEvent],
    clip_paths: list[Path],
    *,
    work_dir: Path,
) -> Path:
    """Return path to video with narration audio (replaces video_path in place)."""
    if not events or not clip_paths:
        return video_path
    if len(events) != len(clip_paths):
        raise ValueError("events and clip_paths length mismatch")

    work_dir.mkdir(parents=True, exist_ok=True)
    narration_wav = work_dir / "narration_track.wav"
    _build_timeline_wav(narration_wav, events, clip_paths)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to mux narration")

    temp_out = work_dir / "animation_narrated.mp4"
    # apad keeps the full video when speech ends before the last frame.
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(narration_wav),
        "-filter_complex",
        "[1:a]apad[a]",
        "-map",
        "0:v:0",
        "-map",
        "[a]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        str(temp_out),
    ]
    log.info("mux narration onto %s", video_path.name)
    subprocess.run(cmd, check=True, capture_output=True)
    temp_out.replace(video_path)
    tag_mp4_bt709_limited_range(video_path)
    return video_path


def _build_timeline_wav(
    dest: Path,
    events: list[SpeechEvent],
    clip_paths: list[Path],
) -> None:
    video_duration_s = _max_timeline_end(events, clip_paths)
    n_samples = int(_SAMPLE_RATE * (video_duration_s + 0.5))
    mix = [0] * n_samples

    for event, clip in zip(events, clip_paths, strict=True):
        offset = int(event.start_seconds * _SAMPLE_RATE)
        samples = _read_pcm16_mono(clip)
        for i, sample in enumerate(samples):
            idx = offset + i
            if idx >= len(mix):
                break
            mixed = mix[idx] + sample
            mix[idx] = max(-32768, min(32767, mixed))

    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(_SAMPLE_RATE)
        frames = b"".join(
            int(sample).to_bytes(2, "little", signed=True) for sample in mix
        )
        handle.writeframes(frames)


def _max_timeline_end(events: list[SpeechEvent], clip_paths: list[Path]) -> float:
    end = 0.0
    for event, clip in zip(events, clip_paths, strict=True):
        dur = _wav_duration_s(clip)
        end = max(end, event.start_seconds + dur)
    return end


def _wav_duration_s(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def _read_pcm16_mono(path: Path) -> list[int]:
    with wave.open(str(path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise ValueError(f"Expected mono 16-bit WAV: {path}")
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    samples = [
        int.from_bytes(raw[i : i + 2], "little", signed=True) for i in range(0, len(raw), 2)
    ]
    if rate != _SAMPLE_RATE and samples:
        # Simple resample for Piper (22.05k) → 24k spike path.
        ratio = _SAMPLE_RATE / rate
        resampled: list[int] = []
        for out_i in range(int(len(samples) * ratio)):
            src_i = min(len(samples) - 1, int(out_i / ratio))
            resampled.append(samples[src_i])
        return resampled
    return samples
