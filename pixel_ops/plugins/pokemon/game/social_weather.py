from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from pixel_ops.data_sources.weather import WeatherState
from pixel_ops.events.base import EventCategory, EventPriority, WorkEvent


@dataclass(frozen=True)
class WorldMoodState:
    world_state: str
    social_activity: str
    encounter_rate: float
    dominant_types: tuple[str, ...]
    mood: str
    companion_emotion: str
    meeting_type: str | None = None
    intensity: float = 0.0
    particles: tuple[str, ...] = ()


class SocialWeatherSystem:
    """Turns operational/social events into ambient world pressure."""

    def __init__(self, event_ttl_minutes: int = 35):
        self.event_ttl = timedelta(minutes=event_ttl_minutes)
        self._events: list[WorkEvent] = []

    def observe(self, event: WorkEvent) -> None:
        self._events.append(event)

    def state(
        self,
        now: datetime,
        weather: WeatherState | None = None,
        calendar_event=None,
    ) -> WorldMoodState:
        self._prune(now)
        activity = sum(_event_weight(event) for event in self._events)
        if weather and any(effect in weather.effects for effect in ("rain", "wind", "cloudy")):
            activity += 0.25

        recent_incident = self._latest(EventCategory.INCIDENT)
        recent_meeting = self._latest(EventCategory.MEETING)
        recent_deploy = self._latest(EventCategory.DEPLOY_STARTED) or self._latest(EventCategory.DEPLOY_COMPLETED)
        quiet = self._latest(EventCategory.SOCIAL_QUIET)

        if recent_incident:
            return self._state("stormy_night", "high", 1.6, ("ghost", "dark", "electric"), "tense", "tense", 1.0, ("rain", "sparks"))
        if recent_meeting:
            return self._meeting_state(recent_meeting, activity)
        if recent_deploy:
            return self._state("forge_city", "high", 1.35, ("fire", "dragon", "steel"), "charged", "excited", 0.75, ("sparks",))
        if _is_friday(now) and activity >= 0.8:
            return self._state("festival_town", "medium", 1.25, ("fairy", "fire", "normal"), "celebrating", "celebrating", 0.65, ("lanterns",))
        if quiet or activity < 0.4:
            return self._state("quiet_route", "low", 0.75, ("grass", "normal"), "calm", _sleepy_or_calm(now), 0.2, ())
        if activity >= 2.5:
            return self._state("electric_city", "high", 1.4, ("electric", "fire", "normal"), "busy", "excited", 0.85, ("sparks", "crowd"))
        if activity >= 1.0:
            return self._state("lively_town", "medium", 1.15, ("electric", "normal", "fairy"), "curious", "curious", 0.55, ("crowd",))
        return self._state("ambient_route", "low", 1.0, ("grass", "normal"), "calm", _sleepy_or_calm(now), 0.35, ())

    def _meeting_state(self, event: WorkEvent, activity: float) -> WorldMoodState:
        meeting_type = event.metadata.get("meeting_type") or "default"
        mood = event.metadata.get("meeting_mood") or "focused"
        emotion = event.metadata.get("companion_emotion") or "curious"
        types = _metadata_types(event) or ("psychic", "fairy")
        particles = {
            "incident_call": ("rain", "sparks"),
            "one_on_one": ("lanterns",),
            "retro": ("embers", "lanterns"),
            "architecture": ("glyphs",),
            "deploy": ("sparks", "embers"),
            "sprint_review": ("crowd",),
        }.get(meeting_type, ("glyphs",))
        return WorldMoodState(
            world_state=f"meeting_{meeting_type}",
            social_activity="medium" if activity < 2.5 else "high",
            encounter_rate=1.1,
            dominant_types=types,
            mood=mood,
            companion_emotion=emotion,
            meeting_type=meeting_type,
            intensity=min(1.0, 0.55 + activity * 0.12),
            particles=particles,
        )

    @staticmethod
    def _state(
        world_state: str,
        social_activity: str,
        encounter_rate: float,
        dominant_types: tuple[str, ...],
        mood: str,
        companion_emotion: str,
        intensity: float,
        particles: tuple[str, ...],
    ) -> WorldMoodState:
        return WorldMoodState(
            world_state=world_state,
            social_activity=social_activity,
            encounter_rate=encounter_rate,
            dominant_types=dominant_types,
            mood=mood,
            companion_emotion=companion_emotion,
            intensity=intensity,
            particles=particles,
        )

    def _latest(self, category: EventCategory) -> WorkEvent | None:
        for event in reversed(self._events):
            if event.category == category:
                return event
        return None

    def _prune(self, now: datetime) -> None:
        self._events = [
            event for event in self._events
            if event.occurred_at is None or now - event.occurred_at <= self.event_ttl
        ]


def _event_weight(event: WorkEvent) -> float:
    base = {
        EventPriority.LOW: 0.25,
        EventPriority.MEDIUM: 0.75,
        EventPriority.HIGH: 1.25,
        EventPriority.CRITICAL: 2.0,
    }.get(event.priority, 0.5)
    if event.category in (EventCategory.SOCIAL_ACTIVITY, EventCategory.MESSAGE_IMPORTANT):
        base += 0.35
    if event.category in (EventCategory.INCIDENT, EventCategory.DEPLOY_STARTED):
        base += 0.8
    return base


def _metadata_types(event: WorkEvent) -> tuple[str, ...]:
    raw = event.metadata.get("dominant_types", "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _is_friday(now: datetime) -> bool:
    return now.weekday() == 4 and now.hour >= 12


def _sleepy_or_calm(now: datetime) -> str:
    return "sleepy" if now.hour >= 22 or now.hour < 6 else "calm"
