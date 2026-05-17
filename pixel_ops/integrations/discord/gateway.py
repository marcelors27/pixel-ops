from __future__ import annotations

from datetime import datetime
from typing import Any

from pixel_ops.events.event_bus import EventBus
from pixel_ops.events.social_events import SocialSignal, signal_to_work_event
from pixel_ops.integrations.discord.presence import classify_discord_dispatch


class DiscordGatewayAdapter:
    """Gateway dispatch adapter.

    The project intentionally avoids a runtime websocket dependency here. A bot
    runner can pass Gateway dispatch payloads to ``handle_dispatch`` and GACO
    will only retain semantic events.
    """

    def __init__(self, bus: EventBus, bot_user_id: str | None = None, enabled: bool = False):
        self.bus = bus
        self.bot_user_id = bot_user_id
        self.enabled = enabled

    def handle_dispatch(self, payload: dict[str, Any]) -> SocialSignal | None:
        signal = classify_discord_dispatch(payload, bot_user_id=self.bot_user_id)
        if self.enabled and signal:
            self.bus.publish(signal_to_work_event(signal))
        return signal


class DiscordBusEventSource:
    def __init__(self, bus: EventBus, enabled: bool = False, drain_limit: int = 4):
        self.bus = bus
        self.enabled = enabled
        self.drain_limit = drain_limit

    def poll(self, now: datetime):
        if not self.enabled:
            return []
        return self.bus.drain(self.drain_limit)
