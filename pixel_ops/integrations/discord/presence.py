from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pixel_ops.events.social_events import SocialPlatform, SocialSignal, SocialSignalKind, classify_text_signal


def classify_discord_dispatch(payload: dict[str, Any], bot_user_id: str | None = None) -> SocialSignal | None:
    event_type = str(payload.get("t") or payload.get("type") or "")
    data = payload.get("d") if isinstance(payload.get("d"), dict) else payload
    sequence = payload.get("s")
    external_id = str(data.get("id") or sequence or "") or None

    if event_type == "MESSAGE_CREATE":
        text = str(data.get("content", ""))
        kind = classify_text_signal(text, default_kind=SocialSignalKind.CHANNEL_ACTIVITY)
        mentions = data.get("mentions") if isinstance(data.get("mentions"), list) else []
        if bot_user_id and any(str(item.get("id")) == bot_user_id for item in mentions if isinstance(item, dict)):
            kind = SocialSignalKind.MENTION
        return SocialSignal(
            provider=SocialPlatform.DISCORD,
            kind=kind,
            actor=_discord_actor(data),
            space=str(data.get("channel_id", "")) or None,
            intensity=0.75,
            occurred_at=_discord_timestamp(data.get("timestamp")),
            external_id=external_id,
        )

    if event_type == "PRESENCE_UPDATE":
        status = str(data.get("status", ""))
        return SocialSignal(
            provider=SocialPlatform.DISCORD,
            kind=SocialSignalKind.PRESENCE_OFFLINE if status == "offline" else SocialSignalKind.PRESENCE_ONLINE,
            actor=_discord_actor(data),
            intensity=0.25,
            external_id=external_id,
            metadata={"status": status},
        )

    if event_type in ("VOICE_STATE_UPDATE", "VOICE_CHANNEL_STATUS_UPDATE"):
        return SocialSignal(
            provider=SocialPlatform.DISCORD,
            kind=SocialSignalKind.VOICE_ACTIVITY,
            actor=_discord_actor(data),
            space=str(data.get("channel_id", "")) or None,
            intensity=0.9,
            external_id=external_id,
        )

    return None


def _discord_actor(data: dict[str, Any]) -> str | None:
    user = data.get("author") or data.get("user") or {}
    if isinstance(user, dict):
        value = user.get("global_name") or user.get("username") or user.get("id")
        return str(value) if value else None
    return None


def _discord_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
