"""HTTP entrypoint for the co-located worker (matches Tutometry CINEMATH_WORKER_URL)."""

from __future__ import annotations

import json
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse

from cinemath.api.errors import CinemathError
from cinemath.api.worker_core import (
    ArtifactPathError,
    artifact_file_path,
    authorize_bearer,
    cinemath_error_payload,
    worker_post_handler,
)


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class WorkerHTTPHandler(BaseHTTPRequestHandler):
    server_version = "CinemathWorker/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        if not authorize_bearer(self.headers.get("Authorization")):
            _json_response(self, HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Unauthorized"})
            return

        parsed = urlparse(self.path)
        prefix = "/v1/artifacts/"
        if not parsed.path.startswith(prefix):
            _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})
            return

        rel = unquote(parsed.path.removeprefix(prefix))
        parts = [part for part in rel.split("/") if part]
        if len(parts) != 3:
            _json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "Invalid artifact path"},
            )
            return

        job_id, attempt_id, filename = parts
        try:
            file_path = artifact_file_path(job_id, attempt_id, filename)
        except ArtifactPathError:
            _json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "Invalid artifact path"},
            )
            return

        if not file_path.is_file():
            _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "Artifact not found"})
            return

        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        if not authorize_bearer(self.headers.get("Authorization")):
            _json_response(self, HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Unauthorized"})
            return

        handler = worker_post_handler(self.path)
        if handler is None:
            _json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})
            return

        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Invalid JSON"})
            return

        if not isinstance(payload, dict):
            _json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "Expected JSON object"},
            )
            return

        try:
            result = handler(payload)
            _json_response(self, HTTPStatus.OK, result)
        except CinemathError as exc:
            if exc.retryable:
                status = HTTPStatus.SERVICE_UNAVAILABLE
            else:
                status = HTTPStatus.UNPROCESSABLE_ENTITY
            _json_response(self, status, cinemath_error_payload(exc))
        except Exception as exc:  # noqa: BLE001
            _json_response(
                self,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "ok": False,
                    "error_code": "internal",
                    "error": str(exc),
                    "retryable": True,
                },
            )


def serve() -> None:
    port = int(os.environ.get("PORT", os.environ.get("CINEMATH_WORKER_PORT", "8080")))
    server = ThreadingHTTPServer(("0.0.0.0", port), WorkerHTTPHandler)
    print(f"cinemath worker HTTP listening on :{port}", flush=True)
    server.serve_forever()


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
