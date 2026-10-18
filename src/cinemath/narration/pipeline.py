"""End-to-end narration pass after Manim render."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cinemath.core.logger import get_logger
from cinemath.narration.mux import mux_narration
from cinemath.narration.timeline import SpeechEvent, collect_speech_events
from cinemath.narration.tts import synthesize_line

log = get_logger("narration")


def mux_aligned_or_synthesize(
    video_path: Path,
    animation: dict[str, Any],
    *,
    animation_path: Path,
    work_dir: Path,
) -> Path:
    """Mux clips already aligned to beats, or fall back to caption TTS."""
    cues = [
        cue
        for cue in (animation.get("narration") or [])
        if cue.get("wav") and cue.get("spoken")
    ]
    if not cues:
        return apply_narration(video_path, animation_path, work_dir=work_dir)

    events = [
        SpeechEvent(str(cue["spoken"]), float(cue.get("start_seconds") or 0.0)) for cue in cues
    ]
    clips = [work_dir / str(cue["wav"]) for cue in cues]
    missing = [path for path in clips if not path.is_file()]
    if missing:
        log.warning(
            "aligned narration clips missing (%s); synthesizing from captions",
            missing[0].name,
        )
        return apply_narration(video_path, animation_path, work_dir=work_dir)
    return mux_narration(video_path, events, clips, work_dir=work_dir)


def apply_narration(
    video_path: Path,
    animation_path: Path,
    *,
    work_dir: Path | None = None,
) -> Path:
    """Synthesize step narration and mux onto ``video_path``."""
    animation_path = animation_path.resolve()
    video_path = video_path.resolve()
    work_dir = (work_dir or video_path.parent / "narration").resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    script = json.loads(animation_path.read_text(encoding="utf-8"))
    events = collect_speech_events(script)
    events = [ev for ev in events if ev.text.strip()]
    if not events:
        log.info("no narration cues in animation — skipping TTS")
        return video_path

    log.info("narration: %d lines", len(events))
    clip_paths: list[Path] = []
    manifest: list[dict[str, Any]] = []
    for i, event in enumerate(events):
        clip = work_dir / f"line_{i:03d}.wav"
        synthesize_line(event.text, clip)
        clip_paths.append(clip)
        manifest.append(
            {
                "index": i,
                "start_seconds": event.start_seconds,
                "text": event.text,
                "wav": clip.name,
            }
        )

    (work_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return mux_narration(video_path, events, clip_paths, work_dir=work_dir)


def write_manim_sidecar(events: list[SpeechEvent], work_dir: Path) -> Path:
    """Optional sidecar for future Manim ``add_sound`` integration."""
    path = work_dir / "narration_manim.json"
    payload = [{"text": e.text, "start_seconds": e.start_seconds} for e in events]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
