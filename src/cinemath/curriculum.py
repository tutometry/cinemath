"""Syllabus-topic classification and homework PDF extraction."""

from __future__ import annotations

import base64
import json
from typing import Any

from cinemath.api.errors import CinemathError, ErrorCode
from cinemath.teaching.llm import (
    _classify_model,
    _client,
    _create_message,
    _parse_json,
    _text_content,
    classify_text_completion,
)

UNSORTED = "unsorted"
MAX_EXTRACTED_QUESTIONS = 40


def normalize_topic_slug(value: object, allowed: set[str]) -> str:
    slug = str(value or "").strip().lower()
    if slug in allowed:
        return slug
    return UNSORTED


def _syllabus_slugs(syllabus: list[dict[str, str]]) -> set[str]:
    return {item["slug"] for item in syllabus} | {UNSORTED}


def _syllabus_block(syllabus: list[dict[str, str]]) -> str:
    lines = [f"- {item['slug']}: {item['title']}" for item in syllabus]
    lines.append(f"- {UNSORTED}: does not fit a single syllabus topic")
    return "\n".join(lines)


def parse_classify_topic_response(text: str, syllabus: list[dict[str, str]]) -> str:
    try:
        payload = _parse_json(text)
    except (json.JSONDecodeError, ValueError):
        return UNSORTED
    if not isinstance(payload, dict):
        return UNSORTED
    allowed = _syllabus_slugs(syllabus)
    return normalize_topic_slug(payload.get("topic_slug"), allowed)


def parse_extract_assignment_response(
    text: str,
    syllabus: list[dict[str, str]],
) -> list[dict[str, str]]:
    try:
        payload = _parse_json(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise CinemathError.permanent(
            ErrorCode.INVALID_INPUT,
            "Assignment extractor returned invalid JSON.",
        ) from exc
    if not isinstance(payload, dict):
        raise CinemathError.permanent(
            ErrorCode.INVALID_INPUT,
            "Assignment extractor returned invalid JSON.",
        )
    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list):
        raise CinemathError.permanent(
            ErrorCode.INVALID_INPUT,
            "Assignment extractor must return a questions array.",
        )
    allowed = _syllabus_slugs(syllabus)
    questions: list[dict[str, str]] = []
    for item in raw_questions:
        if not isinstance(item, dict):
            continue
        statement = str(item.get("text") or "").strip()
        if not statement:
            continue
        questions.append(
            {
                "text": statement,
                "topic_slug": normalize_topic_slug(item.get("topic_slug"), allowed),
            }
        )
        if len(questions) >= MAX_EXTRACTED_QUESTIONS:
            break
    return questions


def _validate_syllabus(raw: object) -> list[dict[str, str]]:
    if not isinstance(raw, list) or len(raw) == 0:
        raise CinemathError.permanent(
            ErrorCode.INVALID_INPUT,
            "syllabus must be a non-empty list of {slug, title} objects.",
        )
    syllabus: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise CinemathError.permanent(
                ErrorCode.INVALID_INPUT,
                "Each syllabus entry must be an object.",
            )
        slug = str(item.get("slug") or "").strip()
        title = str(item.get("title") or "").strip()
        if not slug or not title:
            raise CinemathError.permanent(
                ErrorCode.INVALID_INPUT,
                "Each syllabus entry needs a slug and title.",
            )
        if slug == UNSORTED:
            raise CinemathError.permanent(
                ErrorCode.INVALID_INPUT,
                "unsorted is reserved and cannot be a syllabus slug.",
            )
        if slug in seen:
            raise CinemathError.permanent(
                ErrorCode.INVALID_INPUT,
                f"Duplicate syllabus slug: {slug}",
            )
        seen.add(slug)
        syllabus.append({"slug": slug, "title": title})
    return syllabus


CLASSIFY_TOPIC_SYSTEM = """You assign a homework problem to exactly one syllabus topic.
Return ONLY JSON: {"topic_slug": "<slug>"}.
Use unsorted if none of the topics is a good fit, or if the problem mixes several topics.
Do not solve the problem. Do not add commentary."""


PDF_MEDIA_TYPE = "application/pdf"
IMAGE_MEDIA_TYPES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})

EXTRACT_ASSIGNMENT_SYSTEM = """You extract individual math problems from a homework file.
The file may be a PDF problem set or a photo of one problem or a whole set.
Skip headers, course info, instructions, and grading notes.
Split numbered problems into separate questions. Split 1a/1b when each part can stand alone;
keep parts together when they share a setup that cannot be split.
If the file contains a single problem, return that one question.
Wrap EVERY math fragment in single-dollar ASCII LaTeX: $...$.
Return ONLY JSON:
{"questions": [{"text": "full problem statement", "topic_slug": "<slug>"}]}
Use unsorted when a question does not fit a single syllabus topic.
Do not solve the problems."""


def attachment_content_block(media_type: str, data: str) -> dict[str, Any]:
    if media_type == PDF_MEDIA_TYPE:
        block_type = "document"
    elif media_type in IMAGE_MEDIA_TYPES:
        block_type = "image"
    else:
        raise CinemathError.permanent(
            ErrorCode.INVALID_INPUT,
            "Only PDF and image uploads are supported.",
        )
    return {
        "type": block_type,
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": data,
        },
    }


def classify_topic(problem_text: str, syllabus: list[dict[str, str]]) -> str:
    text = problem_text.strip()
    if not text:
        return UNSORTED
    raw = classify_text_completion(
        system=CLASSIFY_TOPIC_SYSTEM + "\n\nAllowed topics:\n" + _syllabus_block(syllabus),
        user_text=f"Classify this problem:\n\n{text}",
        max_tokens=256,
    )
    return parse_classify_topic_response(raw, syllabus)


def extract_assignment(
    pdf_base64: str,
    syllabus: list[dict[str, str]],
    *,
    media_type: str = "application/pdf",
) -> list[dict[str, str]]:
    try:
        base64.b64decode(pdf_base64, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise CinemathError.permanent(
            ErrorCode.INVALID_INPUT,
            "pdf_base64 is not valid base64.",
        ) from exc

    client = _client()
    message = _create_message(
        client,
        system=EXTRACT_ASSIGNMENT_SYSTEM + "\n\nAllowed topics:\n" + _syllabus_block(syllabus),
        messages=[
            {
                "role": "user",
                "content": [
                    attachment_content_block(media_type, pdf_base64),
                    {
                        "type": "text",
                        "text": "Extract every math problem from this file.",
                    },
                ],
            }
        ],
        max_tokens=8192,
        model=_classify_model(),
    )
    return parse_extract_assignment_response(_text_content(message), syllabus)


def run_classify_topic(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text") or "").strip()
    if not text:
        raise CinemathError.permanent(ErrorCode.INVALID_INPUT, "Problem text is required.")
    syllabus = _validate_syllabus(payload.get("syllabus"))
    topic_slug = classify_topic(text, syllabus)
    return {"ok": True, "topic_slug": topic_slug}


def run_extract_assignment(payload: dict[str, Any]) -> dict[str, Any]:
    pdf_base64 = str(payload.get("pdf_base64") or "").strip()
    if not pdf_base64:
        raise CinemathError.permanent(ErrorCode.INVALID_INPUT, "pdf_base64 is required.")
    media_type = str(payload.get("media_type") or PDF_MEDIA_TYPE).strip() or PDF_MEDIA_TYPE
    attachment_content_block(media_type, pdf_base64)
    syllabus = _validate_syllabus(payload.get("syllabus"))
    questions = extract_assignment(pdf_base64, syllabus, media_type=media_type)
    if not questions:
        raise CinemathError.permanent(
            ErrorCode.INVALID_INPUT,
            "No math problems were found in this file.",
        )
    return {"ok": True, "questions": questions}
