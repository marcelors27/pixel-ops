from __future__ import annotations

import re
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from threading import Lock, Thread
from typing import Any

from pixel_ops.data_sources.weather import WeatherState
from pixel_ops.events.base import WorkEvent
from pixel_ops.plugins.ai.plugin import AiDecisionPlugin, AiDecisionRequest
from pixel_ops.plugins.pokemon.game.knowledge import PokemonKnowledge

EVENT_KEYWORDS = {
    "review_requested": "REVIEW",
    "pull_request": "PR",
    "merge": "MERGE",
}


@dataclass(frozen=True)
class AiPokemonChoice:
    number: int
    reason: str = ""
    appeared_message: str = ""


class PokemonAiPromptBuilder:
    """Builds Pokemon-specific AI decisions while leaving model calls to Pixel OPs AI plugins."""

    def __init__(self, config: dict | None = None, ai_plugin: AiDecisionPlugin | None = None):
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", False))
        self.ai_plugin = ai_plugin
        self.async_enabled = bool(self.config.get("async", True))
        self._lock = Lock()
        self._pending: set[str] = set()
        self._failed: set[str] = set()
        self._results: dict[str, AiPokemonChoice] = {}
        self.last_request_pending = False
        self.debug = _env_bool("PIXEL_OPS_DEBUG_EVENTS") or _env_bool("PIXEL_OPS_DEBUG_AI")

    def choose(
        self,
        event: WorkEvent,
        day_phase: str,
        candidates: list[PokemonKnowledge],
        now: datetime | None = None,
        weather: WeatherState | None = None,
        recent_numbers: tuple[int, ...] = (),
    ) -> AiPokemonChoice | None:
        self.last_request_pending = False
        if not self.enabled or self.ai_plugin is None or not self.ai_plugin.enabled:
            self._debug(f"skip category={event.category.value} reason=disabled")
            return None
        if event.category.value == "ambient":
            self._debug("skip category=ambient reason=ambient-never-uses-openai")
            return None

        if not candidates:
            self._debug(f"skip category={event.category.value} reason=no-candidates")
            return None

        event_keyword = self._event_keyword(event)
        request = self._request(event, day_phase, candidates, now, weather, recent_numbers)
        candidates_by_number = {candidate.number: candidate for candidate in candidates}
        request_key = self._request_key(event, day_phase, candidates, now, weather, recent_numbers)
        if self.async_enabled:
            with self._lock:
                completed = self._results.pop(request_key, None)
                if completed is not None:
                    self._debug(
                        f"complete category={event.category.value} keyword={event_keyword} "
                        f"pokemon={completed.number} source=openai"
                    )
                    return completed
                if request_key in self._failed:
                    self._debug(f"skip category={event.category.value} reason=previous-openai-failed")
                    return None
                if request_key in self._pending:
                    self.last_request_pending = True
                    self._debug(f"pending category={event.category.value} keyword={event_keyword}")
                    return None
                self._pending.add(request_key)
                self.last_request_pending = True
                self._debug(f"start category={event.category.value} keyword={event_keyword} candidates={len(candidates)}")
            Thread(
                target=self._choose_worker,
                args=(request_key, request, candidates_by_number, event_keyword, event),
                daemon=True,
            ).start()
            return None

        result = self.ai_plugin.decide_json(request)
        if not result:
            self._debug(f"fail category={event.category.value} reason=no-openai-result")
            return None
        try:
            choice = self._parse_choice(result, candidates_by_number, event_keyword, event)
            if choice:
                self._debug(f"complete category={event.category.value} keyword={event_keyword} pokemon={choice.number} source=openai")
            return choice
        except (KeyError, TypeError, ValueError):
            self._debug(f"fail category={event.category.value} reason=parse-error")
            return None

    def _choose_worker(
        self,
        request_key: str,
        request: AiDecisionRequest,
        candidates_by_number: dict[int, PokemonKnowledge],
        event_keyword: str,
        event: WorkEvent,
    ) -> None:
        choice = None
        try:
            result = self.ai_plugin.decide_json(request) if self.ai_plugin else None
            if result:
                choice = self._parse_choice(result, candidates_by_number, event_keyword, event)
        except (KeyError, TypeError, ValueError):
            choice = None
        with self._lock:
            self._pending.discard(request_key)
            if choice is not None:
                self._results[request_key] = choice
                self._debug(f"worker-complete keyword={event_keyword} pokemon={choice.number}")
            else:
                self._failed.add(request_key)
                self._debug(f"worker-failed keyword={event_keyword}")

    def _request(
        self,
        event: WorkEvent,
        day_phase: str,
        candidates: list[PokemonKnowledge],
        now: datetime | None,
        weather: WeatherState | None,
        recent_numbers: tuple[int, ...],
    ) -> AiDecisionRequest:
        event_keyword = self._event_keyword(event)
        context = {
            "event": {
                "category": event.category.value,
                "event_keyword": event_keyword,
                "title": self._short(event.title, 96),
                "detail": self._short(event.detail, 96),
                "priority": event.priority.value,
                "source": event.source,
                "repo": event.repo,
                "actor": event.actor,
                "metadata": self._compact_metadata(event.metadata),
            },
            "time": {
                "day_phase": day_phase,
                "local_time": now.isoformat(timespec="minutes") if now else None,
            },
            "weather": self._weather_context(weather),
            "recent_pokemon_numbers": list(recent_numbers),
            "candidates": [candidate.ai_payload() for candidate in candidates],
        }
        return AiDecisionRequest(
            system_prompt=(
                "Pick exactly one Pokemon from candidates only for this operations event, using the event, local "
                "time, day phase, and weather as selection signals. Write one flavorful classic Pokemon-style "
                "appearance line that clearly reacts to the actual event title/detail instead of a generic "
                "appearance. Avoid recent_pokemon_numbers when another suitable candidate is available. Return "
                "compact JSON only. appeared_message may be one or two punchy sentences when useful. In appeared_message, include "
                "the exact event_keyword from the user payload in uppercase and write the chosen Pokemon name in "
                "uppercase. Bad generic examples: 'A wild POKEMON appeared!' or 'POKEMON appeared for the EVENT.'"
            ),
            user_payload=context,
            schema_name="pokemon_choice",
            json_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "number": {"type": "integer", "minimum": 1, "maximum": 151},
                    "reason": {"type": "string"},
                    "appeared_message": {"type": "string"},
                },
                "required": ["number", "reason", "appeared_message"],
            },
            max_output_tokens=900,
        )

    @staticmethod
    def _weather_context(weather: WeatherState | None) -> dict[str, Any] | None:
        if weather is None:
            return None
        return {
            "city": weather.city,
            "temperature_c": weather.temperature_c,
            "apparent_temperature_c": weather.apparent_temperature_c,
            "weather_code": weather.weather_code,
            "effects": weather.effects,
            "rain_mm": weather.rain_mm,
        }

    @staticmethod
    def _compact_metadata(metadata: dict[str, str]) -> dict[str, str]:
        keys = ("state", "starts_at", "labels")
        return {key: metadata[key] for key in keys if key in metadata and metadata[key]}

    def _request_key(
        self,
        event: WorkEvent,
        day_phase: str,
        candidates: list[PokemonKnowledge],
        now: datetime | None,
        weather: WeatherState | None,
        recent_numbers: tuple[int, ...],
    ) -> str:
        weather_key = ""
        if weather:
            weather_key = f"{weather.weather_code}:{','.join(weather.effects)}"
        return "|".join(
            (
                event.external_id or f"{event.source}:{event.category.value}:{event.title}",
                day_phase,
                now.isoformat(timespec="minutes") if now else "",
                weather_key,
                ",".join(str(candidate.number) for candidate in candidates),
                ",".join(str(number) for number in recent_numbers),
            )
        )

    @staticmethod
    def _short(value: str, limit: int) -> str:
        normalized = " ".join(value.split())
        return normalized[:limit]

    def _parse_choice(
        self,
        data: dict[str, Any],
        candidates_by_number: dict[int, PokemonKnowledge],
        event_keyword: str,
        event: WorkEvent,
    ) -> AiPokemonChoice | None:
        number = int(data["number"])
        candidate = candidates_by_number.get(number)
        if candidate is None:
            return None
        appeared_message = " ".join(str(data.get("appeared_message", "")).split())
        appeared_message = self._ensure_message_terms(appeared_message, candidate.name, event_keyword)
        appeared_message = self._enrich_generic_message(appeared_message, candidate.name, event_keyword, event)
        return AiPokemonChoice(
            number=number,
            reason=" ".join(str(data.get("reason", "")).split()),
            appeared_message=appeared_message,
        )

    @staticmethod
    def _event_keyword(event: WorkEvent) -> str:
        return EVENT_KEYWORDS.get(event.category.value, event.category.value.upper())

    @staticmethod
    def _ensure_message_terms(message: str, pokemon_name: str, event_keyword: str) -> str:
        pokemon_upper = pokemon_name.upper()
        event_upper = event_keyword.upper()
        message = re.sub(re.escape(pokemon_name), pokemon_upper, message, flags=re.IGNORECASE)
        parts = []
        if event_upper not in message:
            parts.append(event_upper)
        if pokemon_upper not in message:
            parts.append(pokemon_upper)
        if parts:
            prefix = " ".join(parts)
            return f"{prefix}! {message}" if message else f"{prefix} appeared!"
        return message

    @staticmethod
    def _enrich_generic_message(message: str, pokemon_name: str, event_keyword: str, event: WorkEvent) -> str:
        normalized = re.sub(r"[^a-z0-9]+", " ", message.lower()).strip()
        event_words = re.sub(r"[^a-z0-9]+", " ", event_keyword.lower()).strip()
        if event_words and normalized.startswith(f"{event_words} "):
            normalized = normalized[len(event_words) :].strip()
        pokemon_words = re.sub(r"[^a-z0-9]+", " ", pokemon_name.lower()).strip()
        generic_patterns = {
            f"a wild {pokemon_words} appeared",
            f"wild {pokemon_words} appeared",
            f"{pokemon_words} appeared",
            f"{pokemon_words} appears",
            f"a wild {pokemon_words} appeared for the {event_words}",
            f"{pokemon_words} appeared for the {event_words}",
        }
        if normalized not in generic_patterns and "appeared for the" not in normalized:
            return message

        event_text = " ".join((event.title, event.detail)).strip()
        event_text = event_text or event.category.value.replace("_", " ")
        return f"{event_keyword}! {pokemon_name.upper()} appeared as {event_text}"

    def _debug(self, message: str) -> None:
        if self.debug:
            print(f"[pixel-ops ai-selector] {message}", file=sys.stderr)


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")
