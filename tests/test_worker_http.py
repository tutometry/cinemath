import pytest

from cinemath.api.errors import CinemathError
from cinemath.api.worker_core import (
    WORKER_SHARED_SECRET_ENV,
    ArtifactPathError,
    authorize_bearer,
    resolve_safe_artifact_path,
    run_generation,
)


def test_worker_requires_bearer_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(WORKER_SHARED_SECRET_ENV, "test-secret")
    assert authorize_bearer("Bearer test-secret") is True
    assert authorize_bearer("Bearer wrong") is False
    assert authorize_bearer(None) is False


def test_run_generation_requires_problem_text() -> None:
    with pytest.raises(CinemathError, match="Problem text is required"):
        run_generation({"job_id": "job", "attempt_id": "attempt", "text": ""})


def test_resolve_safe_artifact_path_rejects_traversal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from cinemath.api import worker_core

    root = tmp_path / "artifacts"
    root.mkdir()
    monkeypatch.setattr(worker_core, "ARTIFACT_ROOT", root)

    with pytest.raises(ArtifactPathError):
        resolve_safe_artifact_path("job", "attempt", "..")

    with pytest.raises(ArtifactPathError):
        resolve_safe_artifact_path("..", "attempt", "animation.mp4")

    with pytest.raises(ArtifactPathError):
        resolve_safe_artifact_path("job", "..", "animation.mp4")

    safe = resolve_safe_artifact_path("job-id", "attempt-id", "animation.mp4")
    assert safe == (root / "job-id" / "attempt-id" / "animation.mp4").resolve()


def test_resolve_safe_artifact_path_finds_nested_run_slug(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Flat SaaS filename resolves under pipeline run-slug dir (probe job 8f17fd3b…)."""

    from cinemath.api import worker_core

    # Golden layout from live worker (flat GET /v1/artifacts/{job}/{attempt}/animation.mp4).
    job_id = "8f17fd3b-fb01-4986-83dd-26f8b109d9c5"
    attempt_id = "0e691bcb-2fa2-4126-9b6e-75fe60c9b65d"
    run_slug = "2026-09-18_225650_find-all-real-solutions-to-the-equation"

    root = tmp_path / "artifacts"
    slug_dir = root / job_id / attempt_id / run_slug
    slug_dir.mkdir(parents=True)
    video = slug_dir / "animation.mp4"
    poster = slug_dir / "animation.jpg"
    video.write_bytes(b"mp4-bytes")
    poster.write_bytes(b"jpg-bytes")

    monkeypatch.setattr(worker_core, "ARTIFACT_ROOT", root)

    assert (
        resolve_safe_artifact_path(job_id, attempt_id, "animation.mp4").resolve()
        == video.resolve()
    )
    assert (
        resolve_safe_artifact_path(job_id, attempt_id, "animation.jpg").resolve()
        == poster.resolve()
    )
