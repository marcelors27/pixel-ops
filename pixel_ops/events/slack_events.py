from __future__ import annotations

from datetime import datetime

from pixel_ops.events.base import WorkEvent


class SlackEventSource:
    """Placeholder for Slack/Discord important-message polling."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def poll(self, now: datetime) -> list[WorkEvent]:
        return []
