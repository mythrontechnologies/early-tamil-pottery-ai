"""Minimal HTTP API around ``analyze`` (standard library only; no extra dependency).

    python -m src.inference serve [--host 127.0.0.1] [--port 8765] [--max-mb 25]
                                  [--synthetic-checkpoint PATH|latest]

    GET  /health                     {"status": "ok", "training_ready": false, ...}
    POST /analyze[?artifact_id=ID]   body = raw image bytes (Content-Type image/*)
                                     -> InferenceResult as JSON, with "dataset_type":
                                        research | synthetic | unregistered
                                        (+ "synthetic_analysis" for a synthetic image when
                                        the synthetic pipeline is loaded: --synthetic)
    POST /synthetic/analyze          synthetic images ONLY (422 for anything else):
                                     {"dataset_type": "synthetic", "warning":
                                      "synthetic_not_archaeological", "synthetic_analysis": ...}

A synthetic image (SHA-256 in the synthetic engineering dataset) returns ``dataset_type:
synthetic`` and the warning "Synthetic demonstration — not archaeological evidence"; the optional
synthetic checkpoint is applied to synthetic images ONLY, never to a real or unregistered image.

Safety:

* the client sends image BYTES; the API never accepts a file path or a URL, so it cannot be
  made to read arbitrary files or fetch remote content;
* ``Content-Length`` is required and capped (``--max-mb``); larger bodies are refused unread;
* decoding goes through the same guarded loader as everything else (format allow-list,
  truncation check, decompression-bomb pixel ceiling);
* it binds to 127.0.0.1 by default. Exposing it more widely is a deployment decision
  (docs/DEPLOYMENT.md): there is no authentication.
* nothing is written: no store, no record, no raw file.
"""

from __future__ import annotations

import json
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import InferenceError, analyze

ALLOWED_TYPES = ("image/jpeg", "image/png", "image/tiff", "image/webp", "image/bmp", "application/octet-stream")


def make_handler(max_bytes: int, synthetic_classifier: Any | None = None,
                 synthetic_pipeline: Any | None = None) -> type[BaseHTTPRequestHandler]:
    lock = threading.Lock()             # one GPU pipeline: requests take turns

    class Handler(BaseHTTPRequestHandler):
        server_version = "EarlyTamilPotteryAI/1.0"

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: Any) -> None:     # concise, to stderr
            sys.stderr.write(f"[api] {self.address_string()} {fmt % args}\n")

        def do_GET(self) -> None:
            if urlparse(self.path).path != "/health":
                self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            from src.dataset.readiness import evaluate

            rep = evaluate()
            self._send(HTTPStatus.OK, {"status": "ok", "training_ready": rep.training_ready,
                                       "readiness_reason": rep.reason,
                                       "synthetic_model_loaded": (synthetic_classifier or synthetic_pipeline) is not None,
                                       "synthetic_pipeline_loaded": synthetic_pipeline is not None,
                                       "note": "Analyses return 'Insufficient evidence' where the evidence is insufficient. "
                                               "A synthetic model, if loaded, is applied to synthetic images only."})

        def do_POST(self) -> None:
            url = urlparse(self.path)
            if url.path not in ("/analyze", "/synthetic/analyze"):
                self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            if url.path == "/synthetic/analyze" and synthetic_pipeline is None:
                self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "the synthetic pipeline is not loaded (serve --synthetic)"})
                return
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype not in ALLOWED_TYPES:
                self._send(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": f"Content-Type must be one of {ALLOWED_TYPES}"})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._send(HTTPStatus.LENGTH_REQUIRED, {"error": "Content-Length is required"})
                return
            if length <= 0 or length > max_bytes:
                self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE if length > 0 else HTTPStatus.BAD_REQUEST,
                           {"error": f"body must be 1..{max_bytes} bytes"})
                return
            data = self.rfile.read(length)
            ids = parse_qs(url.query).get("artifact_id")
            artifact = ids[0] if ids else None
            try:
                with lock:
                    result = analyze(data, artifact_id=artifact, max_bytes=max_bytes,
                                     synthetic_classifier=synthetic_classifier, synthetic_pipeline=synthetic_pipeline)
            except InferenceError as exc:
                self._send(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
                return
            if url.path == "/synthetic/analyze":
                if result.dataset_type != "synthetic":
                    self._send(HTTPStatus.UNPROCESSABLE_ENTITY, {
                        "error": "not a synthetic image: synthetic analysis runs only on images of the synthetic "
                                 "engineering dataset", "dataset_type": result.dataset_type, "dataset": result.dataset})
                    return
                self._send(HTTPStatus.OK, {"dataset_type": "synthetic", "warning": "synthetic_not_archaeological",
                                           "dataset": result.dataset, "synthetic_analysis": result.synthetic_analysis})
                return
            self._send(HTTPStatus.OK, result.to_dict())

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765, max_bytes: int = 25 * 2**20,
          synthetic_classifier: Any | None = None, synthetic_pipeline: Any | None = None) -> None:
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"WARNING: binding to {host}: the API has no authentication (docs/DEPLOYMENT.md).", file=sys.stderr)
    httpd = ThreadingHTTPServer((host, port), make_handler(max_bytes, synthetic_classifier, synthetic_pipeline))
    print(f"Serving on http://{host}:{port}  (GET /health, POST /analyze"
          + (", POST /synthetic/analyze" if synthetic_pipeline is not None else "") + ")", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        httpd.server_close()


__all__ = ["ALLOWED_TYPES", "make_handler", "serve"]
