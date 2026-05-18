from __future__ import annotations

import json
import os
import sys
import time
from threading import Thread
from typing import Any

import requests

from pixel_ops.events.event_bus import EventBus
from pixel_ops.events.social_events import signal_to_work_event
from pixel_ops.integrations.slack.classifier import classify_slack_event


class SlackSocketModeClient:
    """Slack Socket Mode receiver for local ambient displays.

    Socket Mode avoids exposing a public HTTP endpoint. GACO opens an outbound
    WebSocket to Slack, acknowledges envelopes, and only publishes semantic
    WorkEvents into the same social bus used by the HTTP listener.
    """

    def __init__(
        self,
        bus: EventBus,
        app_token: str | None = None,
        bot_token: str | None = None,
        bot_user_id: str | None = None,
        enabled: bool = False,
        reconnect_seconds: int = 10,
    ):
        self.bus = bus
        self.app_token = app_token or os.environ.get("PIXEL_OPS_SLACK_APP_TOKEN", "")
        self.bot_token = bot_token or os.environ.get("PIXEL_OPS_SLACK_BOT_TOKEN", "")
        self.bot_user_id = bot_user_id or os.environ.get("PIXEL_OPS_SLACK_BOT_USER_ID", "")
        self.enabled = enabled
        self.reconnect_seconds = max(1, reconnect_seconds)
        self._thread: Thread | None = None
        self._running = False
        self._warned_missing_dependency = False
        self._warned_missing_token = False

    def start(self) -> None:
        if not self.enabled or self._thread:
            return
        if not self.app_token:
            self._warn_once("missing PIXEL_OPS_SLACK_APP_TOKEN; Slack Socket Mode disabled")
            return
        if not self.bot_user_id:
            self.bot_user_id = self._resolve_bot_user_id() or ""
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
                url = self._open_connection_url()
                if not url:
                    time.sleep(self.reconnect_seconds)
                    continue
                ws = websocket.WebSocketApp(
                    url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                ws.run_forever()
            except Exception as error:  # pragma: no cover - defensive for daemon loop
                print(f"[pixel-ops slack-socket] error: {type(error).__name__}: {error}", file=sys.stderr)
            time.sleep(self.reconnect_seconds)

    def _open_connection_url(self) -> str | None:
        try:
            response = requests.post(
                "https://slack.com/api/apps.connections.open",
                headers={"Authorization": f"Bearer {self.app_token}"},
                timeout=8,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as error:
            print(f"[pixel-ops slack-socket] connection open failed: {type(error).__name__}: {error}", file=sys.stderr)
            return None
        if not data.get("ok"):
            print(f"[pixel-ops slack-socket] connection open rejected: {data.get('error', 'unknown_error')}", file=sys.stderr)
            return None
        url = data.get("url")
        return str(url) if url else None

    def _on_message(self, ws, raw_message: str) -> None:
        try:
            envelope = json.loads(raw_message)
        except json.JSONDecodeError:
            return

        envelope_id = envelope.get("envelope_id")
        if envelope_id:
            self._ack(ws, str(envelope_id))

        if envelope.get("type") != "events_api":
            return
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            return
        signal = classify_slack_event(payload, bot_user_id=self.bot_user_id or None)
        if signal:
            self.bus.publish(signal_to_work_event(signal))

    @staticmethod
    def _ack(ws, envelope_id: str) -> None:
        try:
            ws.send(json.dumps({"envelope_id": envelope_id}))
        except Exception:
            return

    @staticmethod
    def _on_error(ws, error) -> None:
        print(f"[pixel-ops slack-socket] websocket error: {error}", file=sys.stderr)

    @staticmethod
    def _on_close(ws, status_code, message) -> None:
        if status_code:
            print(f"[pixel-ops slack-socket] websocket closed status={status_code} message={message}", file=sys.stderr)

    def _resolve_bot_user_id(self) -> str | None:
        if not self.bot_token:
            return None
        try:
            response = requests.post(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                timeout=8,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            return None
        user_id = data.get("user_id") if data.get("ok") else None
        return str(user_id) if user_id else None

    def _websocket_module(self):
        try:
            import websocket

            return websocket
        except ImportError:
            if not self._warned_missing_dependency:
                self._warned_missing_dependency = True
                print(
                    "[pixel-ops slack-socket] install websocket-client to use Slack Socket Mode",
                    file=sys.stderr,
                )
            return None

    def _warn_once(self, message: str) -> None:
        if self._warned_missing_token:
            return
        self._warned_missing_token = True
        print(f"[pixel-ops slack-socket] {message}", file=sys.stderr)
