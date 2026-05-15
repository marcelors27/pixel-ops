from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pixel_ops.data_sources.weather import WeatherState
from pixel_ops.events.base import WorkEvent
from pixel_ops.plugins.ai.plugin import AiDecisionPlugin, AiDecisionRequest
from pixel_ops.plugins.pokemon.game.knowledge import PokemonKnowledge


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
        self.ambient_enabled = bool(self.config.get("ambient", False))
        self.ai_plugin = ai_plugin

    def choose(
        self,
        event: WorkEvent,
        day_phase: str,
        candidates: list[PokemonKnowledge],
        now: datetime | None = None,
        weather: WeatherState | None = None,
        recent_numbers: tuple[int, ...] = (),
    ) -> AiPokemonChoice | None:
        if not self.enabled or self.ai_plugin is None or not self.ai_plugin.enabled:
            return None
        if event.category.value == "ambient" and not self.ambient_enabled:
            return None

        if not candidates:
            return None

        result = self.ai_plugin.decide_json(self._request(event, day_phase, candidates, now, weather, recent_numbers))
        if not result:
            return None
        try:
            return self._parse_choice(result, {candidate.number for candidate in candidates})
        except (KeyError, TypeError, ValueError):
            return None

    def _request(
        self,
        event: WorkEvent,
        day_phase: str,
        candidates: list[PokemonKnowledge],
        now: datetime | None,
        weather: WeatherState | None,
        recent_numbers: tuple[int, ...],
    ) -> AiDecisionRequest:
        context = {
            "event": {
                "category": event.category.value,
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
                "time, day phase, and weather as selection signals. Write one classic Pokemon-style appearance "
                "line. Avoid recent_pokemon_numbers when another suitable candidate is available. Return compact "
                "JSON only. Keep appeared_message concise and mention the chosen Pokemon name."
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
            max_output_tokens=300,
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

    @staticmethod
    def _short(value: str, limit: int) -> str:
        normalized = " ".join(value.split())
        return normalized[:limit]

    def _parse_choice(self, data: dict[str, Any], allowed_numbers: set[int]) -> AiPokemonChoice | None:
        number = int(data["number"])
        if number not in allowed_numbers:
            return None
        appeared_message = " ".join(str(data.get("appeared_message", "")).split())
        return AiPokemonChoice(
            number=number,
            reason=str(data.get("reason", "")),
            appeared_message=appeared_message[:220],
        )
