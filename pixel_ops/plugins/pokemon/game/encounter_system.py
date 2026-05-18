from __future__ import annotations

import os
import sys
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pixel_ops.data_sources.weather import WeatherState
from pixel_ops.plugins.pokemon.pokemon import Pokemon, get_pokemon
from pixel_ops.events.base import EventCategory, EventPriority, EventSource, WorkEvent
from pixel_ops.plugins.pokemon.game.pokemon_selector import PokemonSelector
from pixel_ops.plugins.pokemon.game.state_machine import GamePhase


@dataclass(frozen=True)
class EncounterContext:
    pokemon: Pokemon
    event: WorkEvent | None = None
    rarity: str = "ambient"
    types_used: tuple[str, ...] = ()
    appeared_message: str = ""

    def message_for(self, phase: GamePhase) -> str:
        if phase == GamePhase.ASH_THROWS:
            return "ASH used POKE BALL!"
        if phase == GamePhase.BALL_SHAKE:
            return "..."
        if phase == GamePhase.CAUGHT:
            return self._caught_message()
        if phase in (GamePhase.ENCOUNTER_START, GamePhase.POKEMON_APPEARS):
            return self._appeared_message()
        return "ASH is looking for Pokemon."

    def _appeared_message(self) -> str:
        if self.appeared_message:
            return self.appeared_message
        name = self.pokemon.name.upper()
        if not self.event:
            return f"Wild {name} appeared!"
        return f"A wild {name} appears! {self.event.title}"

    def _caught_message(self) -> str:
        if self.event and self.event.category != EventCategory.AMBIENT:
            return self._resolved_message()
        return f"CAUGHT #{self.pokemon.number:03d} {self.pokemon.name.upper()}"

    def _resolved_message(self) -> str:
        labels = {
            EventCategory.PULL_REQUEST: "PR ENCOUNTER logged",
            EventCategory.MEETING: "MEETING marked",
            EventCategory.BUILD_BROKEN: "CI ALERT contained",
            EventCategory.DEPLOY_STARTED: "DEPLOY tracked",
            EventCategory.DEPLOY_COMPLETED: "DEPLOY completed",
            EventCategory.REVIEW_REQUESTED: "REVIEW noted",
            EventCategory.MESSAGE_IMPORTANT: "MESSAGE noted",
            EventCategory.INCIDENT: "INCIDENT escalated",
            EventCategory.MERGE: "MERGE recorded",
            EventCategory.PR_CLOSED: "PR CLOSED recorded",
            EventCategory.PR_APPROVED: "APPROVAL recorded",
            EventCategory.SOCIAL_ACTIVITY: "SOCIAL weather shifted",
            EventCategory.SOCIAL_PRESENCE: "PRESENCE noted",
            EventCategory.SOCIAL_QUIET: "QUIET period noted",
            EventCategory.AI_USAGE: "AI current measured",
        }
        return labels.get(self.event.category, "EVENT recorded")


class EncounterSystem:
    def __init__(
        self,
        selector: PokemonSelector,
        sources: list[EventSource] | None = None,
        queue_limit: int = 6,
        on_event: Callable[[WorkEvent], None] | None = None,
    ):
        self.selector = selector
        self.sources = sources or []
        self.queue: deque[WorkEvent] = deque(maxlen=queue_limit)
        self.on_event = on_event
        self._seen: set[str] = set()
        self.debug = _env_bool("PIXEL_OPS_DEBUG_EVENTS")

    def poll(self, now: datetime) -> None:
        for source in self.sources:
            for event in source.poll(now):
                self.enqueue(event)

    def enqueue(self, event: WorkEvent) -> None:
        key = event.external_id or f"{event.source}:{event.category.value}:{event.title}"
        if key in self._seen:
            self._debug(f"skip duplicate category={event.category.value} key={key}")
            return
        self._seen.add(key)
        if self.on_event:
            self.on_event(event)
        self.queue.append(event)
        self._debug(f"queued category={event.category.value} key={key} size={len(self.queue)}")

    def next_encounter(
        self,
        day_phase: str,
        now: datetime | None = None,
        weather: WeatherState | None = None,
    ) -> EncounterContext | None:
        if self.queue:
            event = self.queue[0]
            selection = self.selector.select(event, day_phase, now=now, weather=weather)
            if selection is None:
                self._debug(f"waiting category={event.category.value} key={event.external_id or event.title}")
                return None
            self.queue.popleft()
            self._debug(
                f"consume category={event.category.value} source={selection.rarity} "
                f"pokemon={selection.pokemon.number} size={len(self.queue)} "
                f"message={selection.appeared_message[:96]!r}"
            )
            return EncounterContext(
                pokemon=selection.pokemon,
                event=event,
                rarity=selection.rarity,
                types_used=selection.types_used,
                appeared_message=selection.appeared_message,
            )
        return None

    def ambient_context(
        self,
        day_phase: str,
        now: datetime | None = None,
        weather: WeatherState | None = None,
    ) -> EncounterContext:
        selection = self.selector.select_ambient(day_phase, now=now, weather=weather)
        return EncounterContext(
            pokemon=selection.pokemon,
            event=WorkEvent(
                category=EventCategory.AMBIENT,
                title="ASH is looking for Pokemon.",
                priority=EventPriority.LOW,
            ),
            rarity=selection.rarity,
            types_used=selection.types_used,
            appeared_message=selection.appeared_message,
        )

    def idle_context(self) -> EncounterContext:
        return EncounterContext(
            pokemon=get_pokemon(24),
            event=None,
            rarity="idle",
            appeared_message="",
        )

    def _debug(self, message: str) -> None:
        if self.debug:
            print(f"[pixel-ops encounter] {message}", file=sys.stderr)


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")
