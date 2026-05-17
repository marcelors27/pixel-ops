from __future__ import annotations

from datetime import datetime

from pixel_ops.events.ambient_signals import AmbientSignal


class ZoomIntegration:
    """Future Zoom integration boundary.

    Zoom can use polling for upcoming/recent meetings or webhooks for live
    meeting events. Both paths should normalize into AmbientSignal objects.
    """

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def start(self) -> None:
        return

    def poll(self, now: datetime) -> list[AmbientSignal]:
        return []
