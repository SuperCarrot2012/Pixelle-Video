"""Tiny read-only media server for short-drama preview lightboxes."""

from __future__ import annotations

import mimetypes
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

_MEDIA_PREFIX = "/short-drama-media/"
_LOCK = threading.Lock()
_SERVER: ThreadingHTTPServer | None = None
_PORT: int | None = None
_PATH_BY_TOKEN: dict[str, Path] = {}
_TOKEN_BY_PATH: dict[str, str] = {}


class _MediaHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        parsed = urlparse(self.path)
        if not parsed.path.startswith(_MEDIA_PREFIX):
            self.send_error(404)
            return

        token = unquote(parsed.path.removeprefix(_MEDIA_PREFIX))
        with _LOCK:
            path = _PATH_BY_TOKEN.get(token)

        if path is None or not path.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        try:
            size = path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with path.open("rb") as f:
                while chunk := f.read(1024 * 1024):
                    self.wfile.write(chunk)
        except OSError:
            self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        return


def _ensure_server() -> int:
    global _SERVER, _PORT
    with _LOCK:
        if _SERVER is not None and _PORT is not None:
            return _PORT

        server = ThreadingHTTPServer(("0.0.0.0", 0), _MediaHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        _SERVER = server
        _PORT = int(server.server_address[1])
        return _PORT


def register_media_file(image_path: str) -> tuple[str, int]:
    """Register a local image path and return (token, server_port)."""
    port = _ensure_server()
    path = Path(image_path).resolve()
    key = str(path)
    with _LOCK:
        token = _TOKEN_BY_PATH.get(key)
        if token is None:
            token = secrets.token_urlsafe(24)
            _TOKEN_BY_PATH[key] = token
            _PATH_BY_TOKEN[token] = path
    return token, port
