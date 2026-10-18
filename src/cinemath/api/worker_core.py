"""Shared Cinemath worker generation logic (HTTP service + one-shot job CLI)."""

from __future__ import annotations

import json
import mimetypes
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cinemath import __version__
from cinemath.api.errors import CinemathError, ErrorCode
from cinemath.api.generate import generate_lesson
from cinemath.api.models import GenerationOptions, JobContext, ProblemInput
from cinemath.curriculum import run_classify_topic, run_extract_assignment
from cinemath.narration.config import narration_requested

WORKER_SHARED_SECRET_ENV = "WORKER_SHARED_SECRET"
ARTIFACT_ROOT = Path(os.environ.get("CINEMATH_WORKER_ARTIFACT_DIR", "/tmp/cinemath-worker"))


class ArtifactPathError(ValueError):
    """Rejected artifact path (traversal or invalid segment)."""


def _validate_path_segment(segment: str, label: str) -> None:
    if not segment or segment in {".", ".."}:
        raise ArtifactPathError(f"Invalid {label}.")
    if os.sep in segment or (os.altsep and os.altsep in segment):
        raise ArtifactPathError(f"Invalid {label}.")
    if Path(segment).name != segment:
        raise ArtifactPathError(f"Invalid {label}.")


def resolve_safe_run_root(job_id: str, attempt_id: str) -> Path:
    _validate_path_segment(job_id, "job_id")
    _validate_path_segment(attempt_id, "attempt_id")

    artifact_root = ARTIFACT_ROOT.resolve()
    run_root = (artifact_root / job_id / attempt_id).resolve()

    try:
        run_root.relative_to(artifact_root)
    except ValueError as exc:
        raise ArtifactPathError("Artifact run path escapes storage root.") from exc

    return run_root


def _confined_artifact_path(file_path: Path, run_root: Path) -> Path:
    resolved_run = run_root.resolve()
    resolved_file = file_path.resolve()
    try:
        resolved_file.relative_to(resolved_run)
    except ValueError as exc:
        raise ArtifactPathError("Artifact file escapes run directory.") from exc
    return resolved_file


def _nested_run_slug_matches(run_root: Path, filename: str) -> list[Path]:
    """Find filename under one nested run-slug directory (pipeline layout)."""

    matches: list[Path] = []
    for candidate in run_root.glob(f"*/{filename}"):
        if not candidate.is_file():
            continue
        slug_dir = candidate.parent
        if slug_dir.parent.resolve() != run_root.resolve():
            continue
        try:
            _validate_path_segment(slug_dir.name, "run_slug")
        except ArtifactPathError:
            continue
        try:
            matches.append(_confined_artifact_path(candidate, run_root))
        except ArtifactPathError:
            continue
    return matches


def resolve_safe_artifact_path(job_id: str, attempt_id: str, filename: str) -> Path:
    """Resolve a file under ARTIFACT_ROOT/{job_id}/{attempt_id}; reject escapes."""

    _validate_path_segment(filename, "filename")
    run_root = resolve_safe_run_root(job_id, attempt_id)

    direct = run_root / filename
    if direct.is_file():
        return _confined_artifact_path(direct, run_root)

    nested = _nested_run_slug_matches(run_root, filename)
    if nested:
        return max(nested, key=lambda path: path.stat().st_mtime)

    return _confined_artifact_path(direct, run_root)


def authorize_bearer(header_value: str | None) -> bool:
    secret = os.environ.get(WORKER_SHARED_SECRET_ENV, "").strip()
    if not secret:
        return False
    if not header_value or not header_value.startswith("Bearer "):
        return False
    return header_value.removeprefix("Bearer ").strip() == secret


def _maybe_poster_path(video_path: Path) -> Path | None:
    if not video_path.exists():
        return None
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    poster_path = video_path.with_suffix(".jpg")
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-ss",
                "00:00:02",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(poster_path),
            ],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return poster_path if poster_path.exists() else None


def artifact_download_path(job_id: str, attempt_id: str, filename: str) -> str:
    return f"/v1/artifacts/{job_id}/{attempt_id}/{filename}"


def artifact_file_path(job_id: str, attempt_id: str, filename: str) -> Path:
    return resolve_safe_artifact_path(job_id, attempt_id, filename)


def run_generation(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = str(payload.get("job_id") or "").strip()
    attempt_id = str(payload.get("attempt_id") or "").strip()
    text = str(payload.get("text") or "").strip()
    if not job_id or not attempt_id:
        raise CinemathError.permanent(
            ErrorCode.INVALID_INPUT,
            "job_id and attempt_id are required.",
        )
    if not text:
        raise CinemathError.permanent(
            ErrorCode.INVALID_INPUT,
            "Problem text is required.",
        )

    options_payload = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    skip_render = bool(options_payload.get("skip_render", False))
    quality = str(options_payload.get("quality") or "m")
    composition = str(options_payload.get("composition") or "board")
    enable_narration = narration_requested(options_payload=options_payload)

    output_root = resolve_safe_run_root(job_id, attempt_id)
    output_root.mkdir(parents=True, exist_ok=True)

    result = generate_lesson(
        ProblemInput(text=text),
        context=JobContext(job_id=job_id, attempt_id=attempt_id),
        options=GenerationOptions(
            quality=quality,
            composition=composition,
            skip_render=skip_render,
            enable_narration=enable_narration,
            output_root=output_root,
            keep_media=False,
        ),
    )

    lesson_markdown = ""
    if result.lesson_path and result.lesson_path.exists():
        lesson_markdown = result.lesson_path.read_text(encoding="utf-8")

    verification_payload: dict[str, Any] | None = None
    if result.verification is not None:
        verification_payload = {
            "status": result.verification.status.value,
            "method": result.verification.method,
            "notes": result.verification.notes,
            "details": result.verification.details,
        }

    artifacts: list[dict[str, str]] = []
    if result.video_path and result.video_path.exists():
        artifacts.append(
            {
                "kind": "video",
                "name": result.video_path.name,
                "mime_type": mimetypes.guess_type(result.video_path.name)[0] or "video/mp4",
                "download_path": artifact_download_path(job_id, attempt_id, result.video_path.name),
            }
        )
        poster = _maybe_poster_path(result.video_path)
        if poster is not None:
            artifacts.append(
                {
                    "kind": "poster",
                    "name": poster.name,
                    "mime_type": "image/jpeg",
                    "download_path": artifact_download_path(job_id, attempt_id, poster.name),
                }
            )

    animation = None
    if result.animation_path and result.animation_path.exists():
        try:
            animation = json.loads(result.animation_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            animation = None

    return {
        "ok": True,
        "engine_version": __version__,
        "lesson_markdown": lesson_markdown,
        "verification": verification_payload,
        "artifacts": artifacts,
        "animation": animation,
        "manifest": {
            "engine_version": result.manifest.engine_version,
            "schema_version": result.manifest.schema_version,
            "job_id": result.manifest.job_id,
            "attempt_id": result.manifest.attempt_id,
        },
    }


def worker_post_handler(
    path: str,
) -> Callable[[dict[str, Any]], dict[str, Any]] | None:
    route = path.rstrip("/")
    if route == "/v1/generate":
        return run_generation
    if route == "/v1/classify-topic":
        return run_classify_topic
    if route == "/v1/extract-assignment":
        return run_extract_assignment
    return None


def cinemath_error_payload(exc: CinemathError) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": exc.code.value,
        "error": exc.message,
        "retryable": exc.retryable,
    }


def serialize_result(result: dict[str, Any]) -> str:
    return json.dumps(result)
