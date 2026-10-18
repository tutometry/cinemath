import base64

import pytest

from cinemath.api.errors import CinemathError
from cinemath.api.worker_core import run_generation, worker_post_handler
from cinemath.curriculum import (
    UNSORTED,
    attachment_content_block,
    parse_classify_topic_response,
    parse_extract_assignment_response,
    run_classify_topic,
    run_extract_assignment,
)

SYLLABUS = [
    {"slug": "limits", "title": "Limits"},
    {"slug": "differentiation", "title": "Differentiation"},
    {"slug": "related-rates", "title": "Related rates"},
    {"slug": "integration", "title": "Integration"},
]


def test_parse_classify_topic_accepts_allowed_slug() -> None:
    assert (
        parse_classify_topic_response('{"topic_slug": "related-rates"}', SYLLABUS)
        == "related-rates"
    )


def test_parse_classify_topic_falls_back_to_unsorted() -> None:
    assert parse_classify_topic_response('{"topic_slug": "series"}', SYLLABUS) == UNSORTED
    assert parse_classify_topic_response("not json", SYLLABUS) == UNSORTED


def test_parse_extract_assignment_normalizes_topics() -> None:
    raw = """```json
    {"questions": [
      {"text": "Find the limit as x approaches 0.", "topic_slug": "limits"},
      {"text": "A related rates ladder problem.", "topic_slug": "not-a-topic"},
      {"text": "   ", "topic_slug": "integration"}
    ]}
    ```"""
    questions = parse_extract_assignment_response(raw, SYLLABUS)
    assert questions == [
        {"text": "Find the limit as x approaches 0.", "topic_slug": "limits"},
        {"text": "A related rates ladder problem.", "topic_slug": UNSORTED},
    ]


def test_run_classify_topic_requires_text() -> None:
    with pytest.raises(CinemathError, match="Problem text is required"):
        run_classify_topic({"syllabus": SYLLABUS, "text": "  "})


def test_run_extract_assignment_rejects_bad_base64() -> None:
    with pytest.raises(CinemathError, match="not valid base64"):
        run_extract_assignment({"syllabus": SYLLABUS, "pdf_base64": "%%%"})


def test_attachment_block_uses_image_for_screenshots_and_document_for_pdfs() -> None:
    image = attachment_content_block("image/png", "aaaa")
    pdf = attachment_content_block("application/pdf", "aaaa")
    assert image["type"] == "image"
    assert image["source"]["media_type"] == "image/png"
    assert pdf["type"] == "document"
    assert pdf["source"]["media_type"] == "application/pdf"


def test_run_extract_assignment_rejects_unsupported_media_before_calling_the_model() -> None:
    encoded = base64.b64encode(b"not-an-image").decode("ascii")
    with pytest.raises(CinemathError, match="Only PDF and image"):
        run_extract_assignment(
            {"syllabus": SYLLABUS, "pdf_base64": encoded, "media_type": "image/bmp"}
        )


def test_worker_post_routes() -> None:
    assert worker_post_handler("/v1/generate") is run_generation
    assert worker_post_handler("/v1/classify-topic/") is run_classify_topic
    assert worker_post_handler("/v1/extract-assignment") is run_extract_assignment
    assert worker_post_handler("/v1/unknown") is None
