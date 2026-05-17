from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from pixel_ops.events.base import EventCategory, EventPriority, WorkEvent


class AmbientProvider(str, Enum):
    SLACK = "slack"
    DISCORD = "discord"
    TEAMS = "teams"
    ZOOM = "zoom"
    CALENDAR = "calendar"
    GITHUB = "github"


class AmbientSignalKind(str, Enum):
    DIRECT_MESSAGE = "direct_message"
    MENTION = "mention"
    REACTION = "reaction"
    ACTIVITY_SPIKE = "activity_spike"
    QUIET_PERIOD = "quiet_period"
    PRESENCE_ONLINE = "presence_online"
    PRESENCE_OFFLINE = "presence_offline"
    VOICE_ACTIVITY = "voice_activity"
    MEETING_SOON = "meeting_soon"
    MEETING_STARTED = "meeting_started"
    MEETING_ENDED = "meeting_ended"
    PARTICIPANT_JOINED = "participant_joined"
    PARTICIPANT_LEFT = "participant_left"
    INCIDENT_SIGNAL = "incident_signal"
    DEPLOY_SIGNAL = "deploy_signal"
    REVIEW_SIGNAL = "review_signal"


@dataclass(frozen=True)
class AmbientSignal:
    provider: AmbientProvider
    kind: AmbientSignalKind
    actor: str | None = None
    space: str | None = None
    title: str = ""
    intensity: float = 1.0
    occurred_at: datetime | None = None
    external_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


INCIDENT_KEYWORDS = ("sev", "incident", "outage", "down", "erro", "falha", "critical", "p0", "p1")
DEPLOY_KEYWORDS = ("deploy", "release", "ship", "rollback", "production")
REVIEW_KEYWORDS = ("pull request", "pr ", "merge", "review", "github")


def classify_text_kind(text: str, *, default_kind: AmbientSignalKind) -> AmbientSignalKind:
    normalized = f" {text.lower()} "
    if any(keyword in normalized for keyword in INCIDENT_KEYWORDS):
        return AmbientSignalKind.INCIDENT_SIGNAL
    if any(keyword in normalized for keyword in DEPLOY_KEYWORDS):
        return AmbientSignalKind.DEPLOY_SIGNAL
    if any(keyword in normalized for keyword in REVIEW_KEYWORDS):
        return AmbientSignalKind.REVIEW_SIGNAL
    return default_kind


def ambient_signal_to_work_event(signal: AmbientSignal) -> WorkEvent:
    category, priority, title, detail, types = _event_shape(signal)
    metadata = {
        "ambient_provider": signal.provider.value,
        "ambient_kind": signal.kind.value,
        "ambient_intensity": f"{signal.intensity:.2f}",
        "dominant_types": ",".join(types),
        **signal.metadata,
    }
    return WorkEvent(
        category=category,
        title=signal.title or title,
        detail=detail,
        priority=priority,
        source=signal.provider.value,
        actor=signal.actor,
        external_id=signal.external_id,
        occurred_at=signal.occurred_at,
        metadata=metadata,
    )


def _event_shape(signal: AmbientSignal) -> tuple[EventCategory, EventPriority, str, str, tuple[str, ...]]:
    provider_name = signal.provider.value.capitalize()
    actor = signal.actor or "Someone"
    if signal.kind == AmbientSignalKind.DIRECT_MESSAGE:
        return EventCategory.MESSAGE_IMPORTANT, EventPriority.MEDIUM, "New direct message received", "", ("normal", "electric")
    if signal.kind == AmbientSignalKind.MENTION:
        return EventCategory.MESSAGE_IMPORTANT, EventPriority.HIGH, f"You were mentioned by {actor}", "", ("electric", "normal")
    if signal.kind == AmbientSignalKind.INCIDENT_SIGNAL:
        return EventCategory.INCIDENT, EventPriority.CRITICAL, "A strange disturbance spreads across the infrastructure...", "", ("ghost", "dark")
    if signal.kind == AmbientSignalKind.DEPLOY_SIGNAL:
        return EventCategory.DEPLOY_STARTED, EventPriority.HIGH, "The forge lights up for a deploy", "", ("fire", "dragon")
    if signal.kind == AmbientSignalKind.REVIEW_SIGNAL:
        return EventCategory.REVIEW_REQUESTED, EventPriority.MEDIUM, "A review signal echoes nearby", "", ("psychic", "fighting")
    if signal.kind == AmbientSignalKind.REACTION:
        return EventCategory.SOCIAL_ACTIVITY, EventPriority.LOW, f"{provider_name} energy flickers", "", ("fairy", "electric")
    if signal.kind == AmbientSignalKind.ACTIVITY_SPIKE:
        return EventCategory.SOCIAL_ACTIVITY, EventPriority.MEDIUM, f"{provider_name} city grows busier", "", ("electric", "fire")
    if signal.kind in (AmbientSignalKind.VOICE_ACTIVITY, AmbientSignalKind.MEETING_STARTED, AmbientSignalKind.PARTICIPANT_JOINED):
        return EventCategory.MEETING, EventPriority.MEDIUM, "Voices gather in the plaza", "", ("psychic", "fairy")
    if signal.kind == AmbientSignalKind.MEETING_SOON:
        return EventCategory.MEETING, EventPriority.MEDIUM, "A meeting ritual approaches", "", ("psychic", "fairy")
    if signal.kind == AmbientSignalKind.MEETING_ENDED:
        return EventCategory.MEETING, EventPriority.LOW, "Meeting ceremony completed", "", ("normal", "fairy")
    if signal.kind == AmbientSignalKind.PRESENCE_ONLINE:
        return EventCategory.SOCIAL_PRESENCE, EventPriority.LOW, f"{actor} entered the city", "", ("normal", "fairy")
    if signal.kind in (AmbientSignalKind.PRESENCE_OFFLINE, AmbientSignalKind.PARTICIPANT_LEFT):
        return EventCategory.SOCIAL_PRESENCE, EventPriority.LOW, f"{actor} left the lantern road", "", ("ghost", "normal")
    return EventCategory.SOCIAL_QUIET, EventPriority.LOW, "The channels grow quiet", "", ("grass", "normal")
