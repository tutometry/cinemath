"""MP4 limited-range color tagging."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from cinemath.render_engine.video_color import tag_mp4_bt709_limited_range


def test_tag_h264_sets_limited_bt709(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe not available")

    video = tmp_path / "stub.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=#0a0a0a:s=320x180:d=0.2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
        capture_output=True,
    )

    tag_mp4_bt709_limited_range(video)

    probe = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=color_range,color_space",
            "-of",
            "json",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream.get("color_range") == "tv"
    assert stream.get("color_space") == "bt709"
