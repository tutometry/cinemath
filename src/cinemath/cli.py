"""CLI: `cinemath solve <input>`."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from cinemath import __version__
from cinemath.api import JobContext, generate_lesson
from cinemath.api.models import GenerationOptions, ProblemInput
from cinemath.core.logger import configure, fmt_path, get_logger

app = typer.Typer(
    name="cinemath",
    help="LLM teaches the math; local templates build the Manim animation.",
    add_completion=False,
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", "-V", callback=_version_callback, is_eager=True
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging."),
) -> None:
    load_dotenv()
    configure(level="DEBUG" if verbose else None)


@app.command("solve")
def solve(
    input_path: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to .txt, .md, or image of the math problem.",
    ),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output root (default ./outputs)."),
    quality: str = typer.Option(
        "m",
        "--quality",
        "-q",
        help="Manim quality: l (480p15), w (720p30 web), m (720p60), h (1080p60).",
    ),
    composition: str = typer.Option(
        "board",
        "--composition",
        "-c",
        help="Layout density: board (default), web (denser landscape), mobile (9:16 portrait).",
    ),
    skip_render: bool = typer.Option(False, "--skip-render", help="Write plan/animation JSON only."),
    keep_media: bool = typer.Option(
        False, "--keep-media", help="Keep Manim cache (media/) in the run directory."
    ),
    narration: bool = typer.Option(
        False,
        "--narration",
        help="Synthesize step narration (Kokoro/Piper) and mux onto the video. Default off.",
    ),
) -> None:
    """Teach a problem with the LLM, then animate it with local templates."""
    log = get_logger("cli")
    log.info("solve %s", fmt_path(input_path))
    context = JobContext(job_id="cli", attempt_id=input_path.stem)
    try:
        result = generate_lesson(
            ProblemInput(source_path=input_path.resolve()),
            context=context,
            options=GenerationOptions(
                output_root=out.resolve() if out else None,
                quality=quality,
                composition=composition,
                skip_render=skip_render,
                keep_media=keep_media,
                enable_narration=narration,
            ),
        )
    except Exception as exc:
        log.error("failed: %s", exc)
        raise typer.Exit(code=1) from exc

    log.info("done — %s", fmt_path(result.run_dir))
    log.info("  plan:       %s", fmt_path(result.plan_path))
    if result.verification is not None:
        log.info("  verify:     %s", result.verification.status.value)
    else:
        log.info("  verify:     (skipped)")
    log.info("  animation:  %s", fmt_path(result.animation_path))
    if skip_render:
        log.info("  video:      (skipped)")
    else:
        log.info("  video:      %s", fmt_path(result.video_path))
    log.info("  engine:     %s (schema %s)", result.manifest.engine_version, result.manifest.schema_version)


@app.command("render")
def render_cmd(
    animation_path: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to animation.json from a prior solve.",
    ),
    out: Path = typer.Option(..., "--out", "-o", help="Output MP4 path."),
    quality: str = typer.Option(
        "w",
        "--quality",
        "-q",
        help="Manim quality: l (480p15), w (720p30 web), m (720p60), h (1080p60).",
    ),
    composition: str = typer.Option(
        "board",
        "--composition",
        "-c",
        help="Layout density: board, web, or mobile.",
    ),
    narration: bool = typer.Option(
        False,
        "--narration",
        help="Mux synthesized narration onto the output video (opt-in).",
    ),
) -> None:
    """Re-render an existing animation.json (no LLM). Useful for composition variants."""
    from cinemath.narration.config import narration_requested
    from cinemath.render_engine.render import render_animation

    log = get_logger("cli")
    log.info(
        "render %s quality=%s composition=%s",
        fmt_path(animation_path),
        quality,
        composition,
    )
    try:
        animation_path = animation_path.resolve()
        work_dir = out.resolve().parent / "narration"
        if narration_requested(option_flag=narration):
            import json

            from cinemath.narration.align import align_animation
            from cinemath.render_engine.validate import validate_animation

            animation = validate_animation(
                json.loads(animation_path.read_text(encoding="utf-8"))
            )
            align_animation(animation, work_dir=work_dir)
            animation_path.write_text(json.dumps(animation, indent=2) + "\n", encoding="utf-8")
        dest = render_animation(
            animation_path,
            output_path=out.resolve(),
            quality=quality,
            composition=composition,
        )
        if narration_requested(option_flag=narration):
            import json

            from cinemath.narration.pipeline import mux_aligned_or_synthesize

            mux_aligned_or_synthesize(
                dest,
                json.loads(animation_path.read_text(encoding="utf-8")),
                animation_path=animation_path,
                work_dir=work_dir,
            )
    except Exception as exc:
        log.error("failed: %s", exc)
        raise typer.Exit(code=1) from exc
    log.info("video: %s", fmt_path(dest))


if __name__ == "__main__":
    app()
