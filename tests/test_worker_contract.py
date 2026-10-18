"""Lock the worker HTTP surface and exported syllabus to contracts/."""

from __future__ import annotations

import json
from pathlib import Path

from cinemath.api.errors import ErrorCode
from cinemath.api.worker_core import worker_post_handler
from cinemath.curriculum import _validate_syllabus

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI = (REPO_ROOT / "contracts" / "cinemath-worker.openapi.yaml").read_text(encoding="utf-8")
SYLLABUS = json.loads(
    (REPO_ROOT / "contracts" / "syllabus.json").read_text(encoding="utf-8")
)

POST_ROUTES = (
    "/v1/generate",
    "/v1/classify-topic",
    "/v1/extract-assignment",
)


def test_openapi_lists_worker_post_routes() -> None:
    for route in POST_ROUTES:
        assert route in OPENAPI
        assert worker_post_handler(route) is not None
    assert worker_post_handler("/v1/unknown") is None
    assert "/v1/artifacts/{job_id}/{attempt_id}/{filename}" in OPENAPI


def test_openapi_lists_worker_error_codes() -> None:
    for code in ErrorCode:
        assert code.value in OPENAPI


def test_exported_syllabus_is_valid_for_classify_and_extract() -> None:
    courses = SYLLABUS["courses"]
    seen_courses: set[str] = set()
    for course in courses:
        slug = course["slug"]
        assert slug not in seen_courses
        seen_courses.add(slug)
        topics = _validate_syllabus(course["topics"])
        assert topics == course["topics"]
