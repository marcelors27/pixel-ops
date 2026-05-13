from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from pixel_ops.plugins.pokemon.pokemon import Pokemon
from pixel_ops.events.base import EventCategory, EventPriority, EventSource, WorkEvent
from pixel_ops.plugins.pokemon.game.pokemon_selector import PokemonSelector
from pixel_ops.plugins.pokemon.game.state_machine import GamePhase


@dataclass(frozen=True)
class EncounterContext:
    pokemon: Pokemon
    event: WorkEvent | None = None
    rarity: str = "ambient"
    types_used: tuple[str, ...] = ()

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
        }
        return labels.get(self.event.category, "EVENT recorded")


class EncounterSystem:
    def __init__(
        self,
        selector: PokemonSelector,
        sources: list[EventSource] | None = None,
        queue_limit: int = 6,
    ):
        self.selector = selector
        self.sources = sources or []
        self.queue: deque[WorkEvent] = deque(maxlen=queue_limit)
        self._seen: set[str] = set()

    def poll(self, now: datetime) -> None:
        for source in self.sources:
            for event in source.poll(now):
                self.enqueue(event)

    def enqueue(self, event: WorkEvent) -> None:
        key = event.external_id or f"{event.source}:{event.category.value}:{event.title}"
        if key in self._seen:
            return
        self._seen.add(key)
        self.queue.append(event)

    def next_encounter(self, day_phase: str) -> EncounterContext | None:
        if self.queue:
            event = self.queue.popleft()
            selection = self.selector.select(event, day_phase)
            return EncounterContext(
                pokemon=selection.pokemon,
                event=event,
                rarity=selection.rarity,
                types_used=selection.types_used,
            )
        return None

    def ambient_context(self, day_phase: str) -> EncounterContext:
        selection = self.selector.select_ambient(day_phase)
        return EncounterContext(
            pokemon=selection.pokemon,
            event=WorkEvent(
                category=EventCategory.AMBIENT,
                title="ASH is looking for Pokemon.",
                priority=EventPriority.LOW,
            ),
            rarity=selection.rarity,
            types_used=selection.types_used,
        )
