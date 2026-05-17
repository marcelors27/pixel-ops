from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pixel_ops.events.ambient_signals import AmbientProvider, AmbientSignal, AmbientSignalKind, classify_text_kind


def classify_teams_event(payload: dict[str, Any]) -> AmbientSignal | None:
    event_type = str(payload.get("type") or payload.get("eventType") or payload.get("changeType") or "")
    resource = str(payload.get("resource") or "")
    text = str(payload.get("text") or payload.get("summary") or payload.get("subject") or "")
    occurred_at = _parse_datetime(payload.get("eventDateTime") or payload.get("createdDateTime"))

    if "presence" in resource or event_type == "presence":
        availability = str(payload.get("availability") or payload.get("status") or "")
        return AmbientSignal(
            provider=AmbientProvider.TEAMS,
            kind=AmbientSignalKind.PRESENCE_OFFLINE if availability.lower() == "offline" else AmbientSignalKind.PRESENCE_ONLINE,
            actor=_actor(payload),
            intensity=0.25,
            occurred_at=occurred_at,
            external_id=_external_id(payload),
            metadata={"availability": availability},
        )

    if "onlineMeeting" in resource or "meeting" in event_type.lower():
        kind = AmbientSignalKind.MEETING_STARTED if "start" in event_type.lower() else AmbientSignalKind.MEETING_SOON
        return AmbientSignal(
            provider=AmbientProvider.TEAMS,
            kind=classify_text_kind(text, default_kind=kind),
            actor=_actor(payload),
            title=text,
            intensity=0.9,
            occurred_at=occurred_at,
            external_id=_external_id(payload),
        )

    if "chat" in resource or "channel" in resource:
        return AmbientSignal(
            provider=AmbientProvider.TEAMS,
            kind=classify_text_kind(text, default_kind=AmbientSignalKind.ACTIVITY_SPIKE),
            actor=_actor(payload),
            space=str(payload.get("teamId") or payload.get("channelId") or payload.get("chatId") or "") or None,
            intensity=0.7,
            occurred_at=occurred_at,
            external_id=_external_id(payload),
        )

    return None


def _actor(payload: dict[str, Any]) -> str | None:
    value = payload.get("from") or payload.get("userId") or payload.get("organizer")
    if isinstance(value, dict):
        value = value.get("displayName") or value.get("id")
    return str(value) if value else None


def _external_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("id") or payload.get("subscriptionId") or payload.get("changeId")
    return str(value) if value else None


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
