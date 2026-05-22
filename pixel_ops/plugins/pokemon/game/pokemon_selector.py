from __future__ import annotations

import random
import os
import sys
from hashlib import sha256
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from pixel_ops.data_sources.weather import WeatherState
from pixel_ops.plugins.pokemon.pokemon import Pokemon, get_pokemon
from pixel_ops.plugins.pokemon.pokemon_api import PokeApiClient
from pixel_ops.events.base import EventCategory, EventPriority, WorkEvent
from pixel_ops.plugins.ai.plugin import AiDecisionPlugin
from pixel_ops.plugins.pokemon.game.ai_selector import PokemonAiPromptBuilder
from pixel_ops.plugins.pokemon.game.biome_system import repo_types, time_types
from pixel_ops.plugins.pokemon.game.knowledge import PokemonKnowledgeBase
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
    EventCategory.SOCIAL_ACTIVITY.value: ("electric", "fire"),
    EventCategory.SOCIAL_PRESENCE.value: ("normal", "fairy"),
    EventCategory.SOCIAL_QUIET.value: ("grass", "normal"),
    EventCategory.AI_USAGE.value: ("electric", "psychic"),
    EventCategory.AMBIENT.value: ("grass", "normal"),
}

PR_EVOLUTION = {
    EventCategory.PULL_REQUEST: (4, 5, 6),
    EventCategory.MERGE: (6,),
}


@dataclass(frozen=True)
class PokemonSelection:
    pokemon: Pokemon
    rarity: str
    types_used: tuple[str, ...]
    appeared_message: str = ""


class PokemonSelector:
    def __init__(
        self,
        pokemon_api: PokeApiClient | None,
        lazy_download: bool = True,
        config: dict | None = None,
        ai_plugin: AiDecisionPlugin | None = None,
        seed: int = 421,
    ):
        self.pokemon_api = pokemon_api
        self.lazy_download = lazy_download
        self.config = config or {}
        self.rng = random.Random(seed)
        self.ai_selector = PokemonAiPromptBuilder(self.config.get("ai_selector", {}), ai_plugin=ai_plugin)
        self.knowledge = PokemonKnowledgeBase.from_path(self.config.get("knowledge_path"), TYPE_FALLBACKS)
        repeat_window = int(self.config.get("repeat_window", 5))
        self.recent_numbers: deque[int] = deque(maxlen=max(0, repeat_window))
        self.debug = _env_bool("PIXEL_OPS_DEBUG_EVENTS")

    def select(
        self,
        event: WorkEvent,
        day_phase: str,
        now: datetime | None = None,
        weather: WeatherState | None = None,
    ) -> PokemonSelection | None:
        primary_types = self._primary_types_for_event(event)
        type_names = self._types_for_event(event, day_phase)
        if event.category in PR_EVOLUTION and event.metadata.get("evolution", "true") != "false":
            number = self._workflow_number(event)
            if number is not None:
                self._debug(f"selected category={event.category.value} source=workflow pokemon={number}")
                return self._selection(number, "workflow", ("fire",))

        candidate_limit = int(self.config.get("ai_selector", {}).get("candidate_limit", 8))
        candidates = self.knowledge.search(
            event,
            type_names,
            day_phase,
            weather=weather,
            limit=max(candidate_limit, candidate_limit * 3),
        )
        candidates = self._diversify_candidates(event, candidates)[:candidate_limit]
        ai_candidates = self._without_recent_candidates(candidates)
        ai_choice = self.ai_selector.choose(
            event,
            day_phase,
            ai_candidates,
            now=now,
            weather=weather,
            recent_numbers=tuple(self.recent_numbers),
        )
        if ai_choice:
            self._debug(
                f"selected category={event.category.value} source=openai pokemon={ai_choice.number} "
                f"message={ai_choice.appeared_message[:96]!r}"
            )
            return self._selection(ai_choice.number, "ai", ("ai",), ai_choice.appeared_message)
        if self.ai_selector.last_request_pending:
            self._debug(f"waiting category={event.category.value} source=openai")
            return None

        rarity = rarity_for_priority(event.priority, self.rng)
        candidates = self._candidate_numbers(primary_types, rarity) if primary_types else ()
        if not candidates:
            candidates = self._candidate_numbers(type_names, rarity)
        candidates = self._without_recent_numbers(candidates)
        number = self.rng.choice(candidates)
        self._debug(f"selected category={event.category.value} source=fallback pokemon={number} rarity={rarity}")
        return self._selection(number, rarity, type_names)

    def select_ambient(
        self,
        day_phase: str,
        now: datetime | None = None,
        weather: WeatherState | None = None,
    ) -> PokemonSelection:
        event = WorkEvent(
            category=EventCategory.AMBIENT,
            title="ASH is looking for Pokemon.",
            priority=EventPriority.LOW,
        )
        return self.select(event, day_phase, now=now, weather=weather)

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
        event_types = _metadata_types(event) or configured.get(event.category.value) or DEFAULT_EVENT_TYPES.get(event.category.value, ())
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

    def _workflow_number(self, event: WorkEvent) -> int | None:
        numbers = PR_EVOLUTION[event.category]
        preferred = numbers[min(len(numbers) - 1, self._priority_index(event.priority))]
        if preferred not in self.recent_numbers:
            return preferred
        alternatives = tuple(number for number in numbers if number not in self.recent_numbers)
        return alternatives[0] if alternatives else None

    def _without_recent_candidates(self, candidates: list[PokemonKnowledge]) -> list[PokemonKnowledge]:
        if not self.recent_numbers:
            return candidates
        filtered = [candidate for candidate in candidates if candidate.number not in self.recent_numbers]
        return filtered or candidates

    def _without_recent_numbers(self, numbers: tuple[int, ...]) -> tuple[int, ...]:
        if not self.recent_numbers:
            return numbers
        filtered = tuple(number for number in numbers if number not in self.recent_numbers)
        return filtered or numbers

    def _selection(
        self,
        number: int,
        rarity: str,
        types_used: tuple[str, ...],
        appeared_message: str = "",
    ) -> PokemonSelection:
        self.recent_numbers.append(number)
        return PokemonSelection(self._load(number), rarity, types_used, appeared_message)

    def _load(self, number: int) -> Pokemon:
        if self.pokemon_api:
            return self.pokemon_api.get(number, allow_download=self.lazy_download)
        return get_pokemon(number - 1)

    def _diversify_candidates(self, event: WorkEvent, candidates: list[PokemonKnowledge]) -> list[PokemonKnowledge]:
        if event.category != EventCategory.MEETING or len(candidates) < 2:
            return candidates

        values = " ".join((event.title, event.detail, " ".join(event.metadata.values()))).lower()
        mr_mime_fits = any(term in values for term in ("focus", "formal", "decision", "approval", "architecture", "noise"))
        if not mr_mime_fits:
            candidates = [candidate for candidate in candidates if candidate.number != 122]

        if len(candidates) <= 1:
            return candidates
        key = event.external_id or f"{event.source}:{event.title}:{event.detail}"
        offset = int(sha256(key.encode("utf-8")).hexdigest()[:8], 16) % len(candidates)
        return [*candidates[offset:], *candidates[:offset]]

    @staticmethod
    def _priority_index(priority: EventPriority) -> int:
        return {
            EventPriority.LOW: 0,
            EventPriority.MEDIUM: 0,
            EventPriority.HIGH: 1,
            EventPriority.CRITICAL: 2,
        }.get(priority, 0)

    def _debug(self, message: str) -> None:
        if self.debug:
            print(f"[pixel-ops pokemon-selector] {message}", file=sys.stderr)


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _metadata_types(event: WorkEvent) -> tuple[str, ...]:
    raw = event.metadata.get("dominant_types", "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())
