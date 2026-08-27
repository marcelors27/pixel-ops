from __future__ import annotations

import json
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

from pixel_ops.core.screens import ScreenRotationController


class ScreenControlServer:
    """Loopback-only HTTP control surface for Studio, remote UI, and tray."""

    def __init__(self, controller: Callable[[], ScreenRotationController | None], host: str = "127.0.0.1", port: int = 8766):
        self.controller = controller
        self.host = host
        self.port = int(port)
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        provider = self.controller

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path.rstrip("/") != "/status":
                    self._send(404, {"error": "Screen control endpoint not found."})
                    return
                controller = provider()
                self._send(200, controller.status() if controller else _unavailable())

            def do_POST(self) -> None:  # noqa: N802
                controller = provider()
                if controller is None:
                    self._send(503, _unavailable())
                    return
                try:
                    body = self._body()
                    path = self.path.rstrip("/")
                    if path == "/select":
                        controller.select(str(body.get("screen_id") or ""), pinned=bool(body.get("pinned", True)))
                    elif path == "/resume":
                        controller.resume()
                    elif path == "/next":
                        controller.next(pin=_optional_bool(body, "pinned"))
                    elif path == "/previous":
                        controller.previous(pin=_optional_bool(body, "pinned"))
                    else:
                        self._send(404, {"error": "Screen control endpoint not found."})
                        return
                    self._send(200, controller.status())
                except KeyError as error:
                    self._send(404, {"error": str(error)})
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    self._send(400, {"error": str(error)})

            def log_message(self, format: str, *args: Any) -> None:
                return None

            def _body(self) -> dict[str, Any]:
                length = min(8192, max(0, int(self.headers.get("content-length", "0"))))
                if length == 0:
                    return {}
                value = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(value, dict):
                    raise TypeError("Request body must be an object")
                return value

            def _send(self, status: int, body: dict[str, Any]) -> None:
                data = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.port = int(self._server.server_address[1])
        self._thread = Thread(target=self._server.serve_forever, name="pixel-ops-screen-control", daemon=True)
        self._thread.start()

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None


def _unavailable() -> dict[str, Any]:
    return {
        "available": False,
        "enabled": False,
        "mode": "offline",
        "active_screen_id": None,
        "active_screen_label": None,
        "next_screen_id": None,
        "next_screen_label": None,
        "activated_at": None,
        "changes_at": None,
        "remaining_ms": None,
        "revision": 0,
        "screens": [],
    }


def _optional_bool(body: dict[str, Any], key: str) -> bool | None:
    return bool(body[key]) if key in body else None
