from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pixel_ops.events.social_events import (
    SocialPlatform,
    SocialSignal,
    SocialSignalKind,
    classify_text_signal,
)


def classify_slack_event(payload: dict[str, Any], bot_user_id: str | None = None) -> SocialSignal | None:
    event = payload.get("event", payload)
    event_type = str(event.get("type", ""))
    event_id = str(payload.get("event_id") or event.get("event_ts") or event.get("ts") or "")
    occurred_at = _slack_datetime(event.get("event_ts") or event.get("ts") or payload.get("event_time"))

    if event_type == "message":
        channel_type = str(event.get("channel_type", ""))
        text = str(event.get("text", ""))
        default_kind = SocialSignalKind.DIRECT_MESSAGE if channel_type == "im" else SocialSignalKind.CHANNEL_ACTIVITY
        kind = classify_text_signal(text, default_kind=default_kind)
        if bot_user_id and f"<@{bot_user_id}>" in text:
            kind = SocialSignalKind.MENTION
        return SocialSignal(
            provider=SocialPlatform.SLACK,
            kind=kind,
            actor=_actor(event),
            space=str(event.get("channel", "")) or None,
            intensity=1.0 if channel_type == "im" else 0.7,
            occurred_at=occurred_at,
            external_id=event_id or None,
            metadata={"channel_type": channel_type},
        )

    if event_type == "app_mention":
        kind = classify_text_signal(str(event.get("text", "")), default_kind=SocialSignalKind.MENTION)
        return SocialSignal(
            provider=SocialPlatform.SLACK,
            kind=kind,
            actor=_actor(event),
            space=str(event.get("channel", "")) or None,
            intensity=1.2,
            occurred_at=occurred_at,
            external_id=event_id or None,
        )

    if event_type == "reaction_added":
        return SocialSignal(
            provider=SocialPlatform.SLACK,
            kind=SocialSignalKind.REACTION,
            actor=_actor(event),
            intensity=0.4,
            occurred_at=occurred_at,
            external_id=event_id or None,
            metadata={"reaction": str(event.get("reaction", ""))},
        )

    if event_type in ("member_joined_channel", "user_change", "team_join"):
        return SocialSignal(
            provider=SocialPlatform.SLACK,
            kind=SocialSignalKind.PRESENCE_ONLINE,
            actor=_actor(event),
            space=str(event.get("channel", "")) or None,
            intensity=0.3,
            occurred_at=occurred_at,
            external_id=event_id or None,
        )

    if event_type in ("call_started", "call_updated"):
        return SocialSignal(
            provider=SocialPlatform.SLACK,
            kind=SocialSignalKind.VOICE_ACTIVITY,
            actor=_actor(event),
            intensity=0.9,
            occurred_at=occurred_at,
            external_id=event_id or None,
        )

    return None


def _actor(event: dict[str, Any]) -> str | None:
    value = event.get("user") or event.get("user_id") or event.get("bot_id")
    return str(value) if value else None


def _slack_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, int):
            return datetime.fromtimestamp(value, timezone.utc)
        return datetime.fromtimestamp(float(str(value)), timezone.utc)
    except ValueError:
        return None
