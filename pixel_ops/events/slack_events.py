from __future__ import annotations

from datetime import datetime

from pixel_ops.events.event_bus import EventBus
from pixel_ops.integrations.slack.source import SlackBusEventSource


class SlackEventSource(SlackBusEventSource):
    def __init__(self, bus: EventBus | None = None, enabled: bool = False, drain_limit: int = 4):
        super().__init__(bus or EventBus(), enabled=enabled, drain_limit=drain_limit)

    def poll(self, now: datetime):
        return super().poll(now)


__all__ = ["SlackEventSource"]
