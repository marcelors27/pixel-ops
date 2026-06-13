from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from threading import Event, Thread
from typing import Any

import requests

from pixel_ops.events.ambient_signals import AmbientProvider, AmbientSignal, AmbientSignalKind
from pixel_ops.events.event_bus import EventBus
from pixel_ops.events.social_events import signal_to_work_event
from pixel_ops.integrations.discord.presence import classify_discord_dispatch
from pixel_ops.integrations.discord.voice_state import DiscordVoiceStateTracker

DISCORD_GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
DISCORD_API_BASE = "https://discord.com/api/v10"
INTENT_GUILDS = 1 << 0
INTENT_GUILD_MEMBERS = 1 << 1
INTENT_GUILD_PRESENCES = 1 << 8
INTENT_GUILD_VOICE_STATES = 1 << 7


class DiscordGatewayClient:
    """Minimal local Discord Gateway client for ambient voice state.

    It intentionally ignores message content and only publishes semantic voice
    channel entry events into Pixel OPs.
    """

    def __init__(
        self,
        bus: EventBus,
        tracker: DiscordVoiceStateTracker,
        token: str | None = None,
        guild_id: str = "",
        bot_user_id: str = "",
        reconnect_seconds: int = 10,
        bot_user_lookup_timeout_seconds: int = 1,
        enabled: bool = False,
    ):
        self.bus = bus
        self.tracker = tracker
        self.token = token or os.environ.get("PIXEL_OPS_DISCORD_BOT_TOKEN", "")
        self.guild_id = guild_id
        self.bot_user_id = bot_user_id
        self.reconnect_seconds = max(1, reconnect_seconds)
        self.bot_user_lookup_timeout_seconds = max(1, int(bot_user_lookup_timeout_seconds))
        self.enabled = enabled
        self._thread: Thread | None = None
        self._running = False
        self._heartbeat_stop = Event()
        self._sequence: int | None = None
        self._warned_missing_dependency = False
        self._warned_missing_token = False
        self._warned_websocket_error = False

    def start(self) -> None:
        if not self.enabled or self._thread:
            return
        if not self.token:
            self._warn_once("missing PIXEL_OPS_DISCORD_BOT_TOKEN; Discord Gateway disabled")
            return
        self._running = True
        self._thread = Thread(target=self._run_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._heartbeat_stop.set()

    def _run_forever(self) -> None:
        while self._running:
            try:
                if not self.bot_user_id:
                    self.bot_user_id = self._resolve_bot_user_id() or ""
                websocket = self._websocket_module()
                if websocket is None:
                    return
                self._heartbeat_stop.clear()
                ws = websocket.WebSocketApp(
                    DISCORD_GATEWAY_URL,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                ws.run_forever()
            except Exception as error:  # pragma: no cover - defensive daemon loop
                print(f"[pixel-ops discord] gateway error: {type(error).__name__}: {error}", file=sys.stderr)
            self._heartbeat_stop.set()
            if self._running:
                time.sleep(self.reconnect_seconds)

    def _on_open(self, ws) -> None:
        return None

    def _on_message(self, ws, raw_message: str) -> None:
        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            return
        sequence = payload.get("s")
        if isinstance(sequence, int):
            self._sequence = sequence
        opcode = payload.get("op")
        data = payload.get("d") if isinstance(payload.get("d"), dict) else {}
        if opcode == 10:
            interval = float(data.get("heartbeat_interval") or 45000) / 1000
            self._start_heartbeat(ws, interval)
            self._send_identify(ws)
            return
        if opcode == 1:
            self._send_heartbeat(ws)
            return
        if opcode != 0:
            return
        self._handle_dispatch(payload)

    def _handle_dispatch(self, payload: dict[str, Any]) -> None:
        event_type = str(payload.get("t") or "")
        data = payload.get("d") if isinstance(payload.get("d"), dict) else {}
        if event_type == "GUILD_CREATE":
            self.tracker.observe_guild(data)
            return
        if event_type == "PRESENCE_UPDATE":
            self.tracker.observe_presence(data)
            return
        if event_type == "VOICE_STATE_UPDATE":
            joined = self.tracker.observe_voice_state(data)
            if joined:
                member, _, channel_id = joined
                self._publish_voice_join(member.name, channel_id, member.channel_name, payload.get("s"))
                return
            return
        signal = classify_discord_dispatch(payload, bot_user_id=self.bot_user_id or None)
        if signal:
            self.bus.publish(signal_to_work_event(signal))

    def _publish_voice_join(self, actor: str, channel_id: str, channel_name: str, sequence: object) -> None:
        snapshot = self.tracker.snapshot()
        members = ",".join(member.name for member in snapshot.members)
        member_ids = ",".join(member.user_id for member in snapshot.members)
        signal = AmbientSignal(
            provider=AmbientProvider.DISCORD,
            kind=AmbientSignalKind.VOICE_ACTIVITY,
            actor=actor,
            space=channel_id,
            title=f"{actor} accessed a voice channel",
            intensity=0.85,
            occurred_at=datetime.now(timezone.utc),
            external_id=f"discord:voice:{channel_id}:{sequence or int(time.time())}",
            metadata={
                "channel_id": channel_id,
                "channel_name": channel_name,
                "voice_members": members,
                "voice_member_ids": member_ids,
            },
        )
        self.bus.publish(signal_to_work_event(signal))

    def _send_identify(self, ws) -> None:
        payload = {
            "op": 2,
            "d": {
                "token": self.token,
                "intents": INTENT_GUILDS | INTENT_GUILD_MEMBERS | INTENT_GUILD_PRESENCES | INTENT_GUILD_VOICE_STATES,
                "properties": {
                    "os": sys.platform,
                    "browser": "pixel-ops",
                    "device": "pixel-ops",
                },
            },
        }
        ws.send(json.dumps(payload))

    def _start_heartbeat(self, ws, interval_seconds: float) -> None:
        def beat() -> None:
            while self._running and not self._heartbeat_stop.wait(interval_seconds):
                self._send_heartbeat(ws)

        Thread(target=beat, daemon=True).start()

    def _send_heartbeat(self, ws) -> None:
        try:
            ws.send(json.dumps({"op": 1, "d": self._sequence}))
        except Exception:
            return

    def _resolve_bot_user_id(self) -> str | None:
        try:
            response = requests.get(
                f"{DISCORD_API_BASE}/users/@me",
                headers={"Authorization": f"Bot {self.token}"},
                timeout=self.bot_user_lookup_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            return None
        user_id = data.get("id")
        return str(user_id) if user_id else None

    def _on_error(self, ws, error) -> None:
        if self._warned_websocket_error:
            return
        self._warned_websocket_error = True
        print(f"[pixel-ops discord] websocket error: {error}", file=sys.stderr)

    @staticmethod
    def _on_close(ws, status_code, message) -> None:
        if status_code:
            print(f"[pixel-ops discord] websocket closed status={status_code} message={message}", file=sys.stderr)

    def _websocket_module(self):
        try:
            import websocket

            return websocket
        except ImportError:
            if not self._warned_missing_dependency:
                self._warned_missing_dependency = True
                print("[pixel-ops discord] install websocket-client to use Discord Gateway", file=sys.stderr)
            return None

    def _warn_once(self, message: str) -> None:
        if self._warned_missing_token:
            return
        self._warned_missing_token = True
        print(f"[pixel-ops discord] {message}", file=sys.stderr)
