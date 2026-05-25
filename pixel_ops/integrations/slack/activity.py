from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from pixel_ops.events.base import WorkEvent
from pixel_ops.events.social_events import SocialSignal, SocialSignalKind, signal_to_work_event


@dataclass
class _ChannelActivity:
    timestamps: deque[datetime] = field(default_factory=deque)
    last_emitted_at: datetime | None = None


class SlackAmbientAggregator:
    def __init__(
        self,
        activity_window_seconds: int = 120,
        activity_threshold: int = 5,
        activity_cooldown_seconds: int = 300,
    ):
        self.activity_window = timedelta(seconds=max(10, activity_window_seconds))
        self.activity_threshold = max(1, activity_threshold)
        self.activity_cooldown = timedelta(seconds=max(10, activity_cooldown_seconds))
        self._channels: dict[str, _ChannelActivity] = {}

    def observe(self, signal: SocialSignal) -> list[WorkEvent]:
        if signal.kind != SocialSignalKind.ACTIVITY_SPIKE:
            return [signal_to_work_event(signal)]
        channel = signal.space or "_unknown"
        now = signal.occurred_at or datetime.now(timezone.utc)
        activity = self._channels.setdefault(channel, _ChannelActivity())
        cutoff = now - self.activity_window
        while activity.timestamps and activity.timestamps[0] < cutoff:
            activity.timestamps.popleft()
        activity.timestamps.append(now)
        if len(activity.timestamps) < self.activity_threshold:
            return []
        if activity.last_emitted_at and now - activity.last_emitted_at < self.activity_cooldown:
            return []
        activity.last_emitted_at = now
        intensity = min(1.4, 0.5 + len(activity.timestamps) / self.activity_threshold * 0.35)
        return [
            signal_to_work_event(
                SocialSignal(
                    provider=signal.provider,
                    kind=SocialSignalKind.ACTIVITY_SPIKE,
                    actor=signal.actor,
                    space=signal.space,
                    title="Slack channel activity is rising",
                    intensity=intensity,
                    occurred_at=now,
                    external_id=signal.external_id,
                    metadata={
                        **signal.metadata,
                        "activity_window_seconds": str(int(self.activity_window.total_seconds())),
                        "activity_count": str(len(activity.timestamps)),
                    },
                )
            )
        ]
