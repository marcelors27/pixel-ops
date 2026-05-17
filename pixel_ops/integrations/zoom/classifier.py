from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pixel_ops.events.ambient_signals import AmbientProvider, AmbientSignal, AmbientSignalKind, classify_text_kind


def classify_zoom_event(payload: dict[str, Any]) -> AmbientSignal | None:
    event_type = str(payload.get("event") or payload.get("type") or "")
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    obj = body.get("object") if isinstance(body.get("object"), dict) else body
    topic = str(obj.get("topic") or obj.get("subject") or "")
    occurred_at = _parse_datetime(payload.get("event_ts") or obj.get("start_time") or obj.get("end_time"))
    external_id = str(obj.get("uuid") or obj.get("id") or payload.get("event_ts") or "") or None

    lowered = event_type.lower()
    if "participant_joined" in lowered:
        return AmbientSignal(
            provider=AmbientProvider.ZOOM,
            kind=AmbientSignalKind.PARTICIPANT_JOINED,
            actor=_participant(obj),
            title=topic,
            intensity=0.6,
            occurred_at=occurred_at,
            external_id=external_id,
        )
    if "participant_left" in lowered:
        return AmbientSignal(
            provider=AmbientProvider.ZOOM,
            kind=AmbientSignalKind.PARTICIPANT_LEFT,
            actor=_participant(obj),
            title=topic,
            intensity=0.35,
            occurred_at=occurred_at,
            external_id=external_id,
        )
    if "meeting.started" in lowered:
        return AmbientSignal(
            provider=AmbientProvider.ZOOM,
            kind=classify_text_kind(topic, default_kind=AmbientSignalKind.MEETING_STARTED),
            title=topic,
            intensity=0.9,
            occurred_at=occurred_at,
            external_id=external_id,
        )
    if "meeting.ended" in lowered:
        return AmbientSignal(
            provider=AmbientProvider.ZOOM,
            kind=AmbientSignalKind.MEETING_ENDED,
            title=topic,
            intensity=0.3,
            occurred_at=occurred_at,
            external_id=external_id,
        )
    return None


def _participant(obj: dict[str, Any]) -> str | None:
    participant = obj.get("participant") if isinstance(obj.get("participant"), dict) else {}
    value = participant.get("user_name") or participant.get("email") or participant.get("id")
    return str(value) if value else None


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, int):
        return datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value, timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
