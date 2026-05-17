from __future__ import annotations

from datetime import datetime

from pixel_ops.events.event_bus import EventBus


class SlackBusEventSource:
    def __init__(self, bus: EventBus, enabled: bool = False, drain_limit: int = 4):
        self.bus = bus
        self.enabled = enabled
        self.drain_limit = drain_limit

    def poll(self, now: datetime):
        if not self.enabled:
            return []
        return self.bus.drain(self.drain_limit)
