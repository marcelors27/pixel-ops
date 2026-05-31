from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from pixel_ops.events.base import EventCategory, EventPriority, WorkEvent
from pixel_ops.events.social_events import SocialSignal, SocialSignalKind, signal_to_work_event


@dataclass
class _ChannelActivity:
    timestamps: deque[datetime] = field(default_factory=deque)
    last_emitted_at: datetime | None = None


@dataclass(frozen=True)
class SlackChannelRule:
    label: str = ""
    tone: str = "ambient"
    weight: float = 1.0
    activity_threshold: int | None = None
    dominant_types: tuple[str, ...] = ()


@dataclass
class _SummaryWindow:
    started_at: datetime | None = None
    total_activity: int = 0
    mentions: int = 0
    direct_messages: int = 0
    spikes: int = 0
    channel_counts: dict[str, int] = field(default_factory=dict)


class SlackAmbientAggregator:
    def __init__(
        self,
        activity_window_seconds: int = 120,
        activity_threshold: int = 5,
        activity_cooldown_seconds: int = 300,
        summary_window_seconds: int = 900,
        channel_rules: dict[str, SlackChannelRule] | None = None,
    ):
        self.activity_window = timedelta(seconds=max(10, activity_window_seconds))
        self.activity_threshold = max(1, activity_threshold)
        self.activity_cooldown = timedelta(seconds=max(10, activity_cooldown_seconds))
        self.summary_window = timedelta(seconds=max(60, summary_window_seconds))
        self.channel_rules = channel_rules or {}
        self._channels: dict[str, _ChannelActivity] = {}
        self._summary = _SummaryWindow()

    def observe(self, signal: SocialSignal) -> list[WorkEvent]:
        self._observe_summary(signal)
        if signal.kind != SocialSignalKind.ACTIVITY_SPIKE:
            events = [self._attention_event(signal)] if signal.kind in (SocialSignalKind.DIRECT_MESSAGE, SocialSignalKind.MENTION) else [signal_to_work_event(signal)]
            summary = self._maybe_emit_summary(signal.occurred_at or datetime.now(timezone.utc))
            return events + ([summary] if summary else [])
        channel = signal.space or "_unknown"
        now = signal.occurred_at or datetime.now(timezone.utc)
        activity = self._channels.setdefault(channel, _ChannelActivity())
        rule = self.channel_rules.get(channel, SlackChannelRule())
        cutoff = now - self.activity_window
        while activity.timestamps and activity.timestamps[0] < cutoff:
            activity.timestamps.popleft()
        activity.timestamps.append(now)
        events: list[WorkEvent] = []
        threshold = rule.activity_threshold or self.activity_threshold
        if len(activity.timestamps) < threshold:
            summary = self._maybe_emit_summary(now)
            return [summary] if summary else []
        if activity.last_emitted_at and now - activity.last_emitted_at < self.activity_cooldown:
            summary = self._maybe_emit_summary(now)
            return [summary] if summary else []
        activity.last_emitted_at = now
        self._summary.spikes += 1
        intensity = min(1.6, (0.5 + len(activity.timestamps) / threshold * 0.35) * rule.weight)
        events.append(
            signal_to_work_event(
                SocialSignal(
                    provider=signal.provider,
                    kind=SocialSignalKind.ACTIVITY_SPIKE,
                    actor=signal.actor,
                    space=signal.space,
                    title=self._activity_title(rule),
                    intensity=intensity,
                    occurred_at=now,
                    external_id=signal.external_id,
                    metadata={
                        **signal.metadata,
                        **self._channel_metadata(channel, rule),
                        "activity_window_seconds": str(int(self.activity_window.total_seconds())),
                        "activity_count": str(len(activity.timestamps)),
                        "activity_threshold": str(threshold),
                    },
                )
            )
        )
        summary = self._maybe_emit_summary(now)
        if summary:
            events.append(summary)
        return events

    @staticmethod
    def rules_from_config(raw: object) -> dict[str, SlackChannelRule]:
        if not isinstance(raw, dict):
            return {}
        rules = {}
        for channel, value in raw.items():
            if not isinstance(value, dict):
                continue
            types = value.get("dominant_types", ())
            if isinstance(types, str):
                dominant_types = tuple(part.strip() for part in types.split(",") if part.strip())
            elif isinstance(types, list):
                dominant_types = tuple(str(part).strip() for part in types if str(part).strip())
            else:
                dominant_types = ()
            threshold = value.get("activity_threshold")
            try:
                activity_threshold = int(threshold) if threshold is not None else None
            except (TypeError, ValueError):
                activity_threshold = None
            try:
                weight = float(value.get("weight", 1.0))
            except (TypeError, ValueError):
                weight = 1.0
            rules[str(channel)] = SlackChannelRule(
                label=str(value.get("label", "")),
                tone=str(value.get("tone", "ambient")),
                weight=max(0.1, weight),
                activity_threshold=activity_threshold,
                dominant_types=dominant_types,
            )
        return rules

    def _attention_event(self, signal: SocialSignal) -> WorkEvent:
        event = signal_to_work_event(
            SocialSignal(
                provider=signal.provider,
                kind=signal.kind,
                actor=signal.actor,
                space=signal.space,
                title="Slack attention signal at the gate" if signal.kind == SocialSignalKind.MENTION else "Slack direct signal arrived",
                intensity=max(signal.intensity, 1.25 if signal.kind == SocialSignalKind.MENTION else 1.1),
                occurred_at=signal.occurred_at,
                external_id=signal.external_id,
                metadata={
                    **signal.metadata,
                    "attention_pressure": "high" if signal.kind == SocialSignalKind.MENTION else "medium",
                    "slack_attention_kind": signal.kind.value,
                },
            )
        )
        return event

    def _observe_summary(self, signal: SocialSignal) -> None:
        now = signal.occurred_at or datetime.now(timezone.utc)
        if self._summary.started_at is None:
            self._summary.started_at = now
        if signal.kind == SocialSignalKind.ACTIVITY_SPIKE:
            channel = signal.space or "_unknown"
            self._summary.total_activity += 1
            self._summary.channel_counts[channel] = self._summary.channel_counts.get(channel, 0) + 1
        elif signal.kind == SocialSignalKind.MENTION:
            self._summary.mentions += 1
        elif signal.kind == SocialSignalKind.DIRECT_MESSAGE:
            self._summary.direct_messages += 1

    def _maybe_emit_summary(self, now: datetime) -> WorkEvent | None:
        started_at = self._summary.started_at
        if started_at is None or now - started_at < self.summary_window:
            return None
        total = self._summary.total_activity
        mentions = self._summary.mentions
        direct_messages = self._summary.direct_messages
        spikes = self._summary.spikes
        channel_counts = dict(self._summary.channel_counts)
        self._summary = _SummaryWindow(started_at=now)
        if total + mentions + direct_messages + spikes == 0:
            return None
        dominant_channel = max(channel_counts, key=channel_counts.get) if channel_counts else ""
        rule = self.channel_rules.get(dominant_channel, SlackChannelRule())
        priority = EventPriority.MEDIUM if mentions or direct_messages or total >= self.activity_threshold else EventPriority.LOW
        metadata = {
            **self._channel_metadata(dominant_channel, rule),
            "ambient_provider": "slack",
            "ambient_kind": "activity_summary",
            "activity_window_seconds": str(int(self.summary_window.total_seconds())),
            "activity_count": str(total),
            "mentions": str(mentions),
            "direct_messages": str(direct_messages),
            "spikes": str(spikes),
            "active_channels": str(len(channel_counts)),
            "dominant_channel": dominant_channel,
            "dominant_types": ",".join(rule.dominant_types or ("electric", "normal")),
        }
        return WorkEvent(
            category=EventCategory.SOCIAL_ACTIVITY,
            title="Slack ambient pressure summary",
            detail="",
            priority=priority,
            source="slack",
            occurred_at=now,
            metadata=metadata,
        )

    def _channel_metadata(self, channel: str, rule: SlackChannelRule) -> dict[str, str]:
        metadata = {
            "channel": channel,
            "channel_tone": rule.tone,
        }
        if rule.label:
            metadata["channel_label"] = rule.label
        if rule.dominant_types:
            metadata["dominant_types"] = ",".join(rule.dominant_types)
        return metadata

    @staticmethod
    def _activity_title(rule: SlackChannelRule) -> str:
        if rule.label:
            return f"Slack {rule.label} energy is rising"
        return "Slack channel activity is rising"
