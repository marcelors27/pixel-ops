from __future__ import annotations

from datetime import datetime

from pixel_ops.events.ambient_signals import AmbientSignal


class TeamsGraphIntegration:
    """Future Microsoft Graph integration boundary.

    Teams data generally arrives through Graph subscriptions or polling. This
    class intentionally exposes normalized AmbientSignal objects so Graph OAuth,
    tenant consent, and webhook details never leak into the renderer.
    """

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def start(self) -> None:
        return

    def poll(self, now: datetime) -> list[AmbientSignal]:
        return []
