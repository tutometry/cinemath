"""Run Manim to render MathSolution."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from cinemath.render_engine.builder import _ANIMATION_JSON_ENV
from cinemath.render_engine.composition import (
    get_composition,
    quality_fps,
    set_composition_env,
)
from cinemath.core.logger import fmt_path, get_logger
from cinemath.render_engine.video_color import tag_mp4_bt709_limited_range

QUALITY_ARGS: dict[str, list[str]] = {
    "l": ["-ql"],  # 854×480 @ 15fps
    "w": ["-qm", "--frame_rate", "30"],  # 1280×720 @ 30fps (web / landing demos)
    "m": ["-qm", "--frame_rate", "60"],  # 1280×720 @ 60fps
    "h": ["-qh"],  # 1920×1080 @ 60fps
}
_SCENE_MODULE = Path(__file__).resolve().with_name("math_solution_scene.py")
log = get_logger("render")
_PARTIAL_CLIP_GLOB = "**/partial_movie_files/**/*.mp4"
_POLL_INTERVAL_S = 0.25


def _quality_args(quality: str) -> list[str]:
    args = QUALITY_ARGS.get(quality)
    if args is None:
        raise ValueError(f"Unknown quality '{quality}'")
    return args


def manim_cli_args(quality: str, composition: str = "board") -> list[str]:
    """Manim CLI flags for a quality + composition pair."""
    if quality not in QUALITY_ARGS:
        raise ValueError(f"Unknown quality '{quality}'")
    preset = get_composition(composition)
    if preset.pixel_width is not None and preset.pixel_height is not None:
        fps = preset.frame_rate if preset.frame_rate is not None else quality_fps(quality)
        return [
            "--resolution",
            f"{preset.pixel_width},{preset.pixel_height}",
            "--frame_rate",
            str(fps),
        ]
    return list(QUALITY_ARGS[quality])


def _stderr_is_tty() -> bool:
    return hasattr(sys.stderr, "isatty") and bool(sys.stderr.isatty())


def _manim_progress_mode() -> str:
    """``display`` streams Manim's per-animation tqdm bars; ``none`` silences them."""
    env = os.environ.get("CINEMATH_MANIM_PROGRESS", "").strip().lower()
    if env in {"0", "false", "no", "off", "none"}:
        return "none"
    if env in {"1", "true", "yes", "on", "display"}:
        return "display"
    return "display" if _stderr_is_tty() else "none"


def _count_partial_clips(media_dir: Path) -> int:
    return len(list(media_dir.glob(_PARTIAL_CLIP_GLOB)))


def _run_manim(cmd: list[str], *, env: dict[str, str], media_dir: Path) -> int:
    """
    Run Manim, surfacing render progress.

    On an interactive terminal Manim's own tqdm bars stream on stderr (one per
    animation). In non-TTY environments we poll partial-movie clips and log
    periodic updates instead.
    """
    progress = _manim_progress_mode()
    if progress == "none" and "--progress_bar" not in cmd:
        cmd = [*cmd, "--progress_bar", "none"]

    if _stderr_is_tty() and progress == "display":
        log.debug("streaming manim stderr (live per-animation progress bars)")
        return subprocess.run(cmd, env=env).returncode

    log.debug("non-interactive manim render — logging clip progress")
    tail: list[str] = []
    process = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None

    def _drain_output() -> None:
        for line in process.stdout:
            tail.append(line)
            if len(tail) > 80:
                tail.pop(0)

    reader = threading.Thread(target=_drain_output, daemon=True)
    reader.start()

    last_logged = 0
    while process.poll() is None:
        clips = _count_partial_clips(media_dir)
        if clips >= last_logged + 5:
            log.info("rendering… %d clips", clips)
            last_logged = clips
        time.sleep(_POLL_INTERVAL_S)

    reader.join(timeout=1.0)
    clips = _count_partial_clips(media_dir)
    if clips > last_logged:
        log.info("rendering… %d clips", clips)

    if process.returncode != 0:
        joined = "".join(tail).strip()
        if joined:
            log.error("manim output:\n%s", joined)
    return int(process.returncode or 0)


def render_animation(
    animation_path: Path,
    *,
    media_dir: Path | None = None,
    output_path: Path | None = None,
    quality: str = "m",
    composition: str = "board",
    cleanup_media: bool = True,
) -> Path:
    """Render animation.json to MathSolution.mp4."""
    preset = set_composition_env(composition)
    quality_args = manim_cli_args(quality, preset.name)
    animation_path = animation_path.resolve()
    if not animation_path.is_file():
        raise FileNotFoundError(animation_path)

    owns_media = media_dir is None
    if owns_media:
        media_dir = Path(tempfile.mkdtemp(prefix="cinemath-manim-"))
    else:
        media_dir = media_dir.resolve()
    media_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env[_ANIMATION_JSON_ENV] = str(animation_path)
    env["CINEMATH_COMPOSITION"] = preset.name
    cmd = [
        sys.executable,
        "-m",
        "manim",
        *quality_args,
        "--verbosity",
        "warning",
        str(_SCENE_MODULE),
        "MathSolution",
        "--media_dir",
        str(media_dir),
    ]
    log.info(
        "manim render quality=%s composition=%s → %s",
        quality,
        preset.name,
        fmt_path(output_path or animation_path),
    )
    if _stderr_is_tty() and _manim_progress_mode() == "display":
        log.info("manim progress bars below ↓")
    log.debug("manim command: %s", " ".join(cmd))
    returncode = _run_manim(cmd, env=env, media_dir=media_dir)
    if returncode != 0:
        if owns_media and cleanup_media and media_dir.exists():
            shutil.rmtree(media_dir, ignore_errors=True)
        raise RuntimeError(f"Manim failed (exit code {returncode}).")
    videos = sorted(media_dir.rglob("MathSolution.mp4"))
    if not videos:
        if owns_media and cleanup_media and media_dir.exists():
            shutil.rmtree(media_dir, ignore_errors=True)
        raise RuntimeError(f"No MathSolution.mp4 under {media_dir}")
    rendered = videos[-1]
    dest = copy_animation(rendered, output_path) if output_path is not None else rendered
    tag_mp4_bt709_limited_range(dest)
    if owns_media and cleanup_media and media_dir.exists():
        shutil.rmtree(media_dir, ignore_errors=True)
    size_mb = dest.stat().st_size / (1024 * 1024)
    log.info("video ready: %s (%.1f MB)", fmt_path(dest), size_mb)
    return dest


def copy_animation(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest
