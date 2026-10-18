#!/usr/bin/env python3
"""Compile catalog quadratic + narrated render for docs (real TTS unless mock is forced)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "docs" / "samples" / "narration-quadratic"


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from cinemath.catalog import plan_quadratic
    from cinemath.narration.align import align_animation
    from cinemath.narration.config import tts_mock
    from cinemath.narration.pipeline import mux_aligned_or_synthesize
    from cinemath.render_engine.render import render_animation
    from cinemath.render_engine.validate import validate_animation
    from cinemath.templates import compile_plan

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    plan = plan_quadratic("Solve for $x$: $x^2 - 5x + 6 = 0$.", a=1, b=-5, c=6)
    animation = validate_animation(compile_plan(plan))
    animation_path = SAMPLE_DIR / "animation.json"
    video_path = SAMPLE_DIR / "animation.mp4"
    narration_dir = SAMPLE_DIR / "narration"

    skip_narration = os.environ.get("CINEMATH_SKIP_NARRATION") == "1"
    if not skip_narration:
        if tts_mock():
            print(
                "WARNING: CINEMATH_TTS_MOCK=1 — narration will be sine beeps, not speech. "
                "Unset it for Kokoro/Piper/macOS say."
            )
        else:
            print("Narration: Kokoro (or Piper / macOS say fallback).")
        align_animation(animation, work_dir=narration_dir)

    animation_path.write_text(json.dumps(animation, indent=2) + "\n", encoding="utf-8")
    (SAMPLE_DIR / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    if os.environ.get("CINEMATH_SKIP_RENDER") == "1":
        print(f"Wrote {animation_path} (skip render)")
        return 0

    try:
        render_animation(
            animation_path,
            output_path=video_path,
            quality="w",
            composition="web",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Manim render failed ({exc}); animation.json is still usable for review.")
        return 1

    if not skip_narration:
        mux_aligned_or_synthesize(
            video_path,
            animation,
            animation_path=animation_path,
            work_dir=narration_dir,
        )
        print(f"Narrated sample: {video_path}")
    else:
        print(f"Silent sample: {video_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
