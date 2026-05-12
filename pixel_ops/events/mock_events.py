from __future__ import annotations

from collections import deque
from datetime import datetime

from pixel_ops.events.base import EventCategory, EventPriority, WorkEvent


class MockEventSource:
    """Deterministic source used by preview/GIF until API connectors are added."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._events = deque(
            [
                WorkEvent(
                    category=EventCategory.PULL_REQUEST,
                    title="Jon opened PR #421",
                    priority=EventPriority.MEDIUM,
                    source="github",
                    repo="frontend",
                    actor="Jon",
                    external_id="421",
                ),
                WorkEvent(
                    category=EventCategory.BUILD_BROKEN,
                    title="CI pipeline failed",
                    priority=EventPriority.HIGH,
                    source="github",
                    repo="backend",
                ),
                WorkEvent(
                    category=EventCategory.DEPLOY_STARTED,
                    title="Production deploy started",
                    priority=EventPriority.HIGH,
                    source="deploy",
                    repo="infra",
                ),
                WorkEvent(
                    category=EventCategory.INCIDENT,
                    title="SEV-1 detected",
                    priority=EventPriority.CRITICAL,
                    source="incident",
                    repo="infra",
                ),
            ]
        )
        self._last_bucket: int | None = None

    def poll(self, now: datetime) -> list[WorkEvent]:
        if not self.enabled or not self._events:
            return []
        bucket = int(now.timestamp()) // 45
        if self._last_bucket == bucket:
            return []
        self._last_bucket = bucket
        return [self._events.popleft()]
