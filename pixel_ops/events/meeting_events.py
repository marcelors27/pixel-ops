from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from pixel_ops.events.base import EventCategory, EventPriority, WorkEvent


class MeetingCeremonyType(str, Enum):
    SPRINT_REVIEW = "sprint_review"
    ONE_ON_ONE = "one_on_one"
    INCIDENT_CALL = "incident_call"
    ARCHITECTURE = "architecture"
    RETRO = "retro"
    DEPLOY = "deploy"
    PLANNING = "planning"
    DEFAULT = "default"


@dataclass(frozen=True)
class MeetingCeremony:
    ceremony_type: MeetingCeremonyType
    mood: str
    dominant_types: tuple[str, ...]
    intro: str
    active: str
    complete: str
    companion_emotion: str


def ceremony_for_title(title: str) -> MeetingCeremony:
    normalized = title.lower()
    if any(term in normalized for term in ("incident", "sev", "war room", "outage")):
        return MeetingCeremony(
            MeetingCeremonyType.INCIDENT_CALL,
            "tense",
            ("ghost", "dark", "legendary"),
            "A legendary disturbance is forming...",
            "The incident arena is active",
            "The disturbance settles",
            "tense",
        )
    if any(term in normalized for term in ("1:1", "1-1", "one on one", "one-on-one")):
        return MeetingCeremony(
            MeetingCeremonyType.ONE_ON_ONE,
            "restorative",
            ("fairy", "normal"),
            "A Pokemon Center room is ready",
            "A quiet rest ceremony begins",
            "The center lights dim softly",
            "calm",
        )
    if any(term in normalized for term in ("retro", "retrospective")):
        return MeetingCeremony(
            MeetingCeremonyType.RETRO,
            "reflective",
            ("fire", "grass"),
            "The town gathers near the campfire",
            "The retro circle is listening",
            "The campfire burns low",
            "curious",
        )
    if any(term in normalized for term in ("architecture", "design review", "system design", "tech design")):
        return MeetingCeremony(
            MeetingCeremonyType.ARCHITECTURE,
            "focused",
            ("psychic", "steel"),
            "The psychic gym doors open",
            "The architecture gym hums quietly",
            "The glyphs fade from the walls",
            "curious",
        )
    if any(term in normalized for term in ("deploy", "release", "go live", "launch")):
        return MeetingCeremony(
            MeetingCeremonyType.DEPLOY,
            "charged",
            ("dragon", "fire", "steel"),
            "The industrial arena warms up",
            "Dragon-forge lights pulse",
            "The forge cools down",
            "excited",
        )
    if any(term in normalized for term in ("review", "demo", "sprint")):
        return MeetingCeremony(
            MeetingCeremonyType.SPRINT_REVIEW,
            "formal",
            ("fighting", "psychic"),
            "The gym leader is waiting",
            "A sprint review challenge begins",
            "Gym battle completed",
            "focused",
        )
    if "planning" in normalized:
        return MeetingCeremony(
            MeetingCeremonyType.PLANNING,
            "focused",
            ("psychic", "normal"),
            "A planning ritual approaches",
            "The planning chamber is open",
            "The maps are rolled away",
            "curious",
        )
    return MeetingCeremony(
        MeetingCeremonyType.DEFAULT,
        "focused",
        ("psychic", "fairy"),
        "A meeting ritual approaches",
        "The meeting circle is active",
        "Meeting ceremony completed",
        "calm",
    )


def work_event_for_meeting(title: str, starts_at: datetime, now: datetime, leader: str | None = None) -> WorkEvent:
    ceremony = ceremony_for_title(title)
    minutes = max(0, int((starts_at - now).total_seconds() // 60))
    if minutes <= 0:
        message = ceremony.active
    elif leader:
        message = f"Gym Leader {leader} is waiting... {title} starts in {minutes}m"
    else:
        message = f"{ceremony.intro}: {title} starts in {minutes}m"
    priority = EventPriority.HIGH if ceremony.ceremony_type == MeetingCeremonyType.INCIDENT_CALL else EventPriority.MEDIUM
    return WorkEvent(
        category=EventCategory.MEETING,
        title=message,
        priority=priority,
        source="calendar",
        external_id=f"{title}:{starts_at.isoformat()}:{ceremony.ceremony_type.value}",
        occurred_at=now,
        metadata={
            "starts_at": starts_at.isoformat(),
            "meeting_type": ceremony.ceremony_type.value,
            "meeting_mood": ceremony.mood,
            "dominant_types": ",".join(ceremony.dominant_types),
            "companion_emotion": ceremony.companion_emotion,
        },
    )
