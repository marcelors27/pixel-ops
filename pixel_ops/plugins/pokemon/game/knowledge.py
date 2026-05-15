from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pixel_ops.data_sources.weather import WeatherState
from pixel_ops.events.base import WorkEvent
from pixel_ops.plugins.pokemon.pokemon import GEN1_NAMES


@dataclass(frozen=True)
class PokemonKnowledge:
    number: int
    name: str
    types: tuple[str, ...] = ()
    lore: str = ""
    keywords: tuple[str, ...] = ()

    def ai_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "number": self.number,
            "name": self.name,
        }
        if self.types:
            payload["types"] = list(self.types)
        if self.lore:
            payload["lore"] = self.lore
        if self.keywords:
            payload["keywords"] = list(self.keywords[:8])
        return payload


class PokemonKnowledgeBase:
    def __init__(self, records: list[PokemonKnowledge]):
        self.records = records

    @classmethod
    def from_path(
        cls,
        path: str | Path | None,
        type_fallbacks: dict[str, tuple[int, ...]],
    ) -> "PokemonKnowledgeBase":
        generated = cls._generated_records(type_fallbacks)
        if not path:
            return cls(generated)

        knowledge_path = Path(path)
        if not knowledge_path.exists():
            return cls(generated)

        try:
            raw = json.loads(knowledge_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls(generated)

        entries = raw.get("pokemon", raw) if isinstance(raw, dict) else raw
        by_number = {record.number: record for record in generated}
        if not isinstance(entries, list):
            return cls(generated)

        for item in entries:
            if not isinstance(item, dict):
                continue
            try:
                number = int(item["number"])
            except (KeyError, TypeError, ValueError):
                continue
            if number < 1 or number > len(GEN1_NAMES):
                continue

            fallback = by_number[number]
            by_number[number] = PokemonKnowledge(
                number=number,
                name=str(item.get("name") or fallback.name),
                types=cls._tuple(item.get("types")) or fallback.types,
                lore=str(item.get("lore") or fallback.lore),
                keywords=cls._tuple(item.get("keywords")) or fallback.keywords,
            )
        return cls([by_number[number] for number in sorted(by_number)])

    def search(
        self,
        event: WorkEvent,
        type_names: tuple[str, ...],
        day_phase: str,
        weather: WeatherState | None = None,
        limit: int = 8,
    ) -> list[PokemonKnowledge]:
        query_terms = self._query_terms(event, type_names, day_phase, weather)
        scored = [(self._score(record, query_terms, type_names), record) for record in self.records]
        scored.sort(key=lambda item: (-item[0], item[1].number))
        selected = [record for score, record in scored if score > 0][:limit]
        if selected:
            return selected
        return self.records[:limit]

    @staticmethod
    def _generated_records(type_fallbacks: dict[str, tuple[int, ...]]) -> list[PokemonKnowledge]:
        types_by_number: dict[int, list[str]] = {number: [] for number in range(1, len(GEN1_NAMES) + 1)}
        for type_name, numbers in type_fallbacks.items():
            for number in numbers:
                if 1 <= number <= len(GEN1_NAMES) and type_name not in types_by_number[number]:
                    types_by_number[number].append(type_name)

        records: list[PokemonKnowledge] = []
        for number, name in enumerate(GEN1_NAMES, start=1):
            type_names = tuple(types_by_number[number])
            records.append(
                PokemonKnowledge(
                    number=number,
                    name=name,
                    types=type_names,
                    lore=PokemonKnowledgeBase._generated_lore(name, type_names),
                    keywords=type_names,
                )
            )
        return records

    @staticmethod
    def _generated_lore(name: str, type_names: tuple[str, ...]) -> str:
        if not type_names:
            return f"{name} brings a neutral Kanto encounter energy to routine dashboard events."
        traits = ", ".join(type_names[:3])
        return f"{name} carries {traits} Kanto energy that can mirror matching work signals."

    @staticmethod
    def _query_terms(
        event: WorkEvent,
        type_names: tuple[str, ...],
        day_phase: str,
        weather: WeatherState | None,
    ) -> set[str]:
        values = [
            event.category.value,
            event.title,
            event.detail,
            event.priority.value,
            event.source,
            event.repo or "",
            event.actor or "",
            day_phase,
            *type_names,
            *event.metadata.values(),
        ]
        if weather:
            values.extend([weather.city, *(weather.effects or ())])
        return {
            token.lower()
            for value in values
            for token in str(value).replace("_", " ").replace("-", " ").split()
            if token
        }

    @staticmethod
    def _score(record: PokemonKnowledge, query_terms: set[str], type_names: tuple[str, ...]) -> int:
        record_terms = PokemonKnowledgeBase._record_terms(record)
        score = len(query_terms & record_terms)
        score += sum(4 for type_name in type_names if type_name in record.types)
        return score

    @staticmethod
    def _record_terms(record: PokemonKnowledge) -> set[str]:
        values = [record.name, record.lore, *record.types, *record.keywords]
        return {
            token.lower()
            for value in values
            for token in str(value).replace("_", " ").replace("-", " ").split()
            if token
        }

    @staticmethod
    def _tuple(value: object) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            return ()
        return tuple(str(item) for item in value if str(item))
