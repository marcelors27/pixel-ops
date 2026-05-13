from __future__ import annotations

import random
from dataclasses import dataclass

from pixel_ops.plugins.pokemon.pokemon import Pokemon, get_pokemon
from pixel_ops.plugins.pokemon.pokemon_api import PokeApiClient
from pixel_ops.events.base import EventCategory, EventPriority, WorkEvent
from pixel_ops.plugins.pokemon.game.biome_system import repo_types, time_types
from pixel_ops.plugins.pokemon.game.rarity import RARITY_POKEMON, rarity_for_priority


TYPE_FALLBACKS = {
    "bug": (10, 12, 13, 15, 46, 47, 48, 49, 123, 127),
    "dark": (24, 42, 94, 130, 150),
    "dragon": (130, 147, 148, 149),
    "electric": (25, 26, 81, 82, 100, 101, 125, 135, 145),
    "fairy": (35, 36, 39, 40, 113, 122),
    "fighting": (56, 57, 66, 67, 68, 106, 107),
    "fire": (4, 5, 6, 37, 38, 58, 59, 77, 78, 126, 136, 146),
    "ghost": (92, 93, 94, 104, 105, 109, 110, 150),
    "grass": (1, 2, 3, 43, 44, 45, 69, 70, 71, 102, 103, 114),
    "ground": (27, 28, 31, 34, 50, 51, 74, 75, 76, 95, 104, 105, 111, 112),
    "legendary": (144, 145, 146, 150, 151),
    "normal": (16, 17, 18, 19, 20, 21, 22, 39, 52, 53, 83, 108, 113, 115, 128, 132, 133, 143),
    "psychic": (63, 64, 65, 79, 80, 96, 97, 102, 103, 121, 122, 124, 150, 151),
    "rock": (74, 75, 76, 95, 111, 112, 138, 139, 140, 141, 142),
    "steel": (81, 82),
    "water": (7, 8, 9, 54, 55, 60, 61, 62, 72, 73, 86, 87, 90, 91, 98, 99, 116, 117, 118, 119, 120, 121, 129, 130, 131, 134),
}

DEFAULT_EVENT_TYPES = {
    EventCategory.PULL_REQUEST.value: ("bug", "electric", "fighting"),
    EventCategory.MEETING.value: ("psychic", "fairy"),
    EventCategory.BUILD_BROKEN.value: ("ghost", "electric"),
    EventCategory.DEPLOY_STARTED.value: ("dragon", "fire"),
    EventCategory.DEPLOY_COMPLETED.value: ("fire", "flying"),
    EventCategory.REVIEW_REQUESTED.value: ("psychic", "fighting"),
    EventCategory.MESSAGE_IMPORTANT.value: ("electric", "normal"),
    EventCategory.INCIDENT.value: ("ghost", "dark", "legendary"),
    EventCategory.MERGE.value: ("dragon", "normal"),
    EventCategory.PR_CLOSED.value: ("ghost", "normal"),
    EventCategory.PR_APPROVED.value: ("electric", "fairy"),
    EventCategory.AMBIENT.value: ("grass", "normal"),
}

PR_EVOLUTION = {
    EventCategory.PULL_REQUEST: (4, 5, 6),
    EventCategory.REVIEW_REQUESTED: (5,),
    EventCategory.MERGE: (6,),
    EventCategory.PR_CLOSED: (6,),
}


@dataclass(frozen=True)
class PokemonSelection:
    pokemon: Pokemon
    rarity: str
    types_used: tuple[str, ...]


class PokemonSelector:
    def __init__(
        self,
        pokemon_api: PokeApiClient | None,
        lazy_download: bool = True,
        config: dict | None = None,
        seed: int = 421,
    ):
        self.pokemon_api = pokemon_api
        self.lazy_download = lazy_download
        self.config = config or {}
        self.rng = random.Random(seed)

    def select(self, event: WorkEvent, day_phase: str) -> PokemonSelection:
        if event.category in PR_EVOLUTION and event.metadata.get("evolution", "true") != "false":
            numbers = PR_EVOLUTION[event.category]
            number = numbers[min(len(numbers) - 1, self._priority_index(event.priority))]
            return PokemonSelection(self._load(number), "workflow", ("fire",))

        rarity = rarity_for_priority(event.priority, self.rng)
        primary_types = self._primary_types_for_event(event)
        type_names = self._types_for_event(event, day_phase)
        candidates = self._candidate_numbers(primary_types, rarity) if primary_types else ()
        if not candidates:
            candidates = self._candidate_numbers(type_names, rarity)
        number = self.rng.choice(candidates)
        return PokemonSelection(self._load(number), rarity, type_names)

    def select_ambient(self, day_phase: str) -> PokemonSelection:
        event = WorkEvent(
            category=EventCategory.AMBIENT,
            title="ASH is looking for Pokemon.",
            priority=EventPriority.LOW,
        )
        return self.select(event, day_phase)

    def _types_for_event(self, event: WorkEvent, day_phase: str) -> tuple[str, ...]:
        event_types = self._primary_types_for_event(event)
        if event.category == EventCategory.AMBIENT:
            combined = [*event_types, *time_types(day_phase)]
        else:
            repos = self.config.get("repo_biomes", {})
            combined = [*event_types, *repo_types(event.repo, repos), *time_types(day_phase)]
            if event.priority == EventPriority.CRITICAL:
                combined.append("legendary")
        return tuple(dict.fromkeys(str(item) for item in combined if item))

    def _primary_types_for_event(self, event: WorkEvent) -> tuple[str, ...]:
        configured = self.config.get("event_pokemon_types", {})
        event_types = configured.get(event.category.value) or DEFAULT_EVENT_TYPES.get(event.category.value, ())
        return tuple(dict.fromkeys(str(item) for item in event_types if item))

    def _candidate_numbers(self, type_names: tuple[str, ...], rarity: str) -> tuple[int, ...]:
        numbers: list[int] = []
        for type_name in type_names:
            numbers.extend(TYPE_FALLBACKS.get(type_name, ()))
        if not numbers:
            numbers.extend(RARITY_POKEMON[rarity])

        rarity_numbers = set(RARITY_POKEMON.get(rarity, ()))
        filtered = [number for number in numbers if number in rarity_numbers]
        if filtered:
            return tuple(filtered)
        return tuple(numbers)

    def _load(self, number: int) -> Pokemon:
        if self.pokemon_api:
            return self.pokemon_api.get(number, allow_download=self.lazy_download)
        return get_pokemon(number - 1)

    @staticmethod
    def _priority_index(priority: EventPriority) -> int:
        return {
            EventPriority.LOW: 0,
            EventPriority.MEDIUM: 0,
            EventPriority.HIGH: 1,
            EventPriority.CRITICAL: 2,
        }.get(priority, 0)
