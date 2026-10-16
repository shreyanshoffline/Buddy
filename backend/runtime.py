"""Lifecycle for Buddy's local backend.

The desktop app and the backend intentionally live in one Python process. A
daemon thread keeps Flask's routes available for local OAuth, Slack setup and
subscription checks without asking users to start a second terminal process.
The backend can still be deployed separately; this module is only the local
runtime adapter.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional


def _bool_env(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _port() -> int:
    try:
        return max(1, min(65535, int(os.environ.get("BUDDY_BACKEND_PORT", "5000"))))
    except ValueError:
        return 5000


def _health_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=0.8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return bool(payload.get("ok"))
    except (OSError, ValueError, KeyError):
        return False


@dataclass
class LocalBackend:
    """A handle for a local backend, including an already-running instance."""

    host: str
    port: int
    server: object | None = None
    thread: threading.Thread | None = None
    external: bool = False

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def started(self) -> bool:
        return self.server is not None or self.external

    def stop(self) -> None:
        """Stop only the server this process created."""
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


_handle: Optional[LocalBackend] = None


def start_local_backend() -> LocalBackend | None:
    """Start or discover Buddy's local backend.

    Set ``BUDDY_START_BACKEND=0`` for a frontend-only run, or use
    ``BUDDY_BACKEND_HOST``/``BUDDY_BACKEND_PORT`` to choose the bind address.
    A second Buddy process reuses the first healthy backend instead of failing
    with a confusing port error.
    """
    global _handle
    if _handle and (_handle.thread is None or _handle.thread.is_alive()):
        return _handle
    if not _bool_env("BUDDY_START_BACKEND", True):
        return None

    host = os.environ.get("BUDDY_BACKEND_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = _port()
    existing = LocalBackend(host, port, external=True)
    if _health_ok(existing.url):
        _handle = existing
        return existing

    try:
        from werkzeug.serving import make_server
        from .app import app

        server = make_server(host, port, app, threaded=True)
    except (ImportError, OSError, RuntimeError):
        # The GUI should remain usable when optional backend dependencies are
        # missing or another service owns the selected port.
        return None

    handle = LocalBackend(host, port, server=server)
    thread = threading.Thread(
        target=server.serve_forever,
        name="buddy-backend",
        daemon=True,
    )
    handle.thread = thread
    thread.start()
    _handle = handle
    return handle


def local_backend_url() -> str | None:
    return _handle.url if _handle and _handle.started else None

