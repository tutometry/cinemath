"""MP4 color metadata for web playback (Manim H.264 is studio-range BT.709)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from cinemath.core.logger import get_logger

log = get_logger("render.color")

# Manim/libx264 output is studio (limited) range; tagging as full range lifts blacks.
_H264_BSF_BT709_LIMITED = (
    "h264_metadata=video_full_range_flag=0:"
    "colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1"
)


def _video_codec(path: Path) -> str | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
        streams = payload.get("streams") or []
        if not streams:
            return None
        name = streams[0].get("codec_name")
        return str(name) if name else None
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def tag_mp4_bt709_limited_range(video_path: Path) -> Path:
    """
    Tag H.264 as limited-range BT.709 (no re-encode).

    Leaves pixel values unchanged; avoids ``color_range=unknown`` and incorrect
    full-range tags that make near-black backgrounds look too dark or too bright
    vs the app canvas / poster.
    """
    video_path = video_path.resolve()
    if not video_path.is_file():
        raise FileNotFoundError(video_path)

    codec = _video_codec(video_path)
    if codec != "h264":
        log.debug("skip color tag for codec=%s path=%s", codec, video_path.name)
        return video_path

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        log.warning("ffmpeg missing; cannot tag %s", video_path.name)
        return video_path

    temp_out = video_path.with_suffix(".color-tagged.mp4")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-c",
        "copy",
        "-bsf:v",
        _H264_BSF_BT709_LIMITED,
        "-movflags",
        "+faststart",
        str(temp_out),
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0 or not temp_out.is_file():
        log.warning(
            "bt709 limited color tag failed for %s: %s",
            video_path.name,
            (result.stderr or result.stdout or "").strip()[:400],
        )
        temp_out.unlink(missing_ok=True)
        return video_path

    temp_out.replace(video_path)
    log.debug("tagged %s bt709 limited range", video_path.name)
    return video_path
