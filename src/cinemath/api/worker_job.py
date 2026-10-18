"""One-shot batch entrypoint (stdin or argv JSON payload)."""

from __future__ import annotations

import json
import sys
from typing import Any

from cinemath.api.errors import CinemathError, ErrorCode
from cinemath.api.worker_core import cinemath_error_payload, run_generation, serialize_result


def _read_payload() -> dict[str, Any]:
    if len(sys.argv) > 1:
        raw = sys.argv[1]
    else:
        raw = sys.stdin.read()

    raw = raw.strip()
    if not raw:
        raise CinemathError.permanent(
            ErrorCode.INVALID_INPUT,
            "Generation payload JSON is required on stdin or argv[1].",
        )

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CinemathError.permanent(
            ErrorCode.INVALID_INPUT,
            "Invalid JSON payload.",
            cause=str(exc),
        ) from exc

    if not isinstance(payload, dict):
        raise CinemathError.permanent(
            ErrorCode.INVALID_INPUT,
            "Expected a JSON object payload.",
        )
    return payload


def main() -> None:
    try:
        payload = _read_payload()
        result = run_generation(payload)
        print(serialize_result(result), flush=True)
    except CinemathError as exc:
        print(serialize_result(cinemath_error_payload(exc)), flush=True)
        raise SystemExit(1 if exc.retryable else 2) from exc
    except Exception as exc:  # noqa: BLE001
        print(
            serialize_result(
                {
                    "ok": False,
                    "error_code": ErrorCode.INTERNAL.value,
                    "error": str(exc),
                    "retryable": True,
                }
            ),
            flush=True,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
