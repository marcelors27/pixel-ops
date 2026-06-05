from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from threading import Thread
from typing import Any

from pixel_ops.events.ambient_signals import ambient_signal_to_work_event
from pixel_ops.events.event_bus import EventBus
from pixel_ops.integrations.zoom.classifier import classify_zoom_event
from pixel_ops.integrations.zoom.participants import ZoomParticipantTracker


class PixelOpsKiteClient:
    def __init__(
        self,
        bus: EventBus,
        *,
        ws_url: str = "",
        token: str = "",
        reconnect_seconds: int = 10,
        enabled: bool = False,
        zoom_tracker: ZoomParticipantTracker | None = None,
    ):
        self.bus = bus
        self.ws_url = ws_url
        self.token = token
        self.reconnect_seconds = max(1, int(reconnect_seconds))
        self.enabled = enabled
        self.zoom_tracker = zoom_tracker
        self._thread: Thread | None = None
        self._running = False
        self._warned_missing_dependency = False
        self._warned_missing_config = False

    def start(self) -> None:
        if not self.enabled or self._thread:
            return
        if not self.ws_url or not self.token:
            self._warn_once("missing PixelOpsKite ws_url or token; Kite disabled")
            return
        self._running = True
        self._thread = Thread(target=self._run_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _run_forever(self) -> None:
        while self._running:
            try:
                websocket = self._websocket_module()
                if websocket is None:
                    return
                ws = websocket.WebSocketApp(
                    self.ws_url,
                    header=[f"Authorization: Bearer {self.token}"],
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                ws.run_forever()
            except Exception as error:  # pragma: no cover - defensive daemon loop
                print(f"[pixel-ops kite] websocket error: {type(error).__name__}: {error}", file=sys.stderr)
            if self._running:
                time.sleep(self.reconnect_seconds)

    def handle_envelope(self, envelope: dict[str, Any]) -> None:
        provider = str(envelope.get("provider") or "")
        if provider == "zoom":
            payload = envelope.get("payload")
            if not isinstance(payload, dict):
                return
            signal = classify_zoom_event(payload)
            if not signal:
                return
            if self.zoom_tracker is not None:
                self.zoom_tracker.observe_signal(signal)
            self.bus.publish(ambient_signal_to_work_event(signal))

    def _on_message(self, ws, raw_message: str) -> None:
        try:
            envelope = json.loads(raw_message)
        except json.JSONDecodeError:
            return
        if not isinstance(envelope, dict) or envelope.get("type") == "hello":
            return
        self.handle_envelope(envelope)

    @staticmethod
    def _on_error(ws, error) -> None:
        print(f"[pixel-ops kite] websocket error: {error}", file=sys.stderr)

    @staticmethod
    def _on_close(ws, status_code, message) -> None:
        if status_code:
            print(f"[pixel-ops kite] websocket closed status={status_code} message={message}", file=sys.stderr)

    def _websocket_module(self):
        try:
            import websocket

            return websocket
        except ImportError:
            if not self._warned_missing_dependency:
                self._warned_missing_dependency = True
                print("[pixel-ops kite] install websocket-client to use PixelOpsKite", file=sys.stderr)
            return None

    def _warn_once(self, message: str) -> None:
        if self._warned_missing_config:
            return
        self._warned_missing_config = True
        print(f"[pixel-ops kite] {message}", file=sys.stderr)


class PixelOpsKiteEventSource:
    def __init__(self, bus: EventBus, enabled: bool = False, drain_limit: int = 4):
        self.bus = bus
        self.enabled = enabled
        self.drain_limit = drain_limit

    def poll(self, now: datetime):
        if not self.enabled:
            return []
        return self.bus.drain(self.drain_limit)
