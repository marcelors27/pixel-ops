from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from pixel_ops.events.platform import PixelOpsEvent


class ObservationEventSource:
    """Adapts a snapshot API to the platform event-source contract."""

    def __init__(self, event_type: str, source_name: str, source: Any, method_name: str = "current", poll_seconds: float | None = None):
        self.event_type = event_type
        self.source_name = source_name
        self.source = source
        self.method_name = method_name
        self.poll_seconds = float(poll_seconds or getattr(source, "poll_seconds", 1.0))

    def poll(self, now: datetime) -> list[PixelOpsEvent]:
        value = getattr(self.source, self.method_name)(now)
        return [PixelOpsEvent.observation(self.event_type, self.source_name, value, now)]


class CallableObservationSource:
    def __init__(self, event_type: str, source_name: str, callback: Callable[[datetime], Any], poll_seconds: float = 30):
        self.event_type = event_type
        self.source_name = source_name
        self.callback = callback
        self.poll_seconds = poll_seconds

    def poll(self, now: datetime) -> list[PixelOpsEvent]:
        return [PixelOpsEvent.observation(self.event_type, self.source_name, self.callback(now), now)]

