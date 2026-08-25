from __future__ import annotations

import os
import unicodedata
from datetime import datetime, timezone
from typing import Any

import requests

from pixel_ops.data_sources.projects import ProjectItem, ProjectSnapshot


CAPACITIES_API_BASE_URL = "https://api.capacities.io"
CAPACITIES_API_VERSION = "0.1.0"


class CapacitiesProjectSource:
    def __init__(
        self,
        enabled: bool = True,
        token_env: str = "PIXEL_OPS_CAPACITIES_TOKEN",
        structure_names: list[str] | tuple[str, ...] | str | None = None,
        poll_seconds: int = 300,
        max_projects: int = 24,
        timeout_seconds: int = 10,
        api_base_url: str = CAPACITIES_API_BASE_URL,
    ):
        self.enabled = enabled
        self.token_env = token_env
        self.structure_names = _names(structure_names) or ["Projeto", "Project"]
        self.poll_seconds = max(1, int(poll_seconds))
        self.max_projects = max(1, min(200, int(max_projects)))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.api_base_url = api_base_url.rstrip("/")
        self._last_poll_at: datetime | None = None
        self._snapshot: ProjectSnapshot | None = None

    def current(self, now: datetime | None = None) -> ProjectSnapshot | None:
        if not self.enabled:
            return None
        base_now = now or datetime.now().astimezone()
        if self._last_poll_at and (base_now - self._last_poll_at).total_seconds() < self.poll_seconds:
            return self._snapshot
        self._last_poll_at = base_now
        try:
            self._snapshot = self._fetch_snapshot(base_now)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            if self._snapshot is None:
                self._snapshot = ProjectSnapshot((), base_now, provider="capacities", status="unavailable")
        return self._snapshot

    def _fetch_snapshot(self, now: datetime) -> ProjectSnapshot:
        token = os.environ.get(self.token_env, "").strip()
        if not token:
            raise ValueError(f"{self.token_env} is required for Capacities projects")
        structures_payload = self._get_json(token, "/space/structures")
        structures = structures_payload.get("structures", []) if isinstance(structures_payload, dict) else []
        structure = _find_structure(structures, self.structure_names)
        if structure is None:
            return ProjectSnapshot((), now, provider="capacities", status="missing_project_type")
        definitions = _definition_map(structure)
        payload = self._get_json(
            token,
            "/objects/structure",
            params={"id": str(structure.get("id") or ""), "pageSize": min(100, self.max_projects)},
        )
        summaries = payload.get("results", []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []
        objects = [
            self._get_json(token, "/object", params={"id": str(summary.get("id") or "")})
            for summary in summaries[: self.max_projects]
            if isinstance(summary, dict) and summary.get("id")
        ]
        projects = tuple(_project_from_object(item, definitions) for item in objects if isinstance(item, dict))
        return ProjectSnapshot(projects, now, provider="capacities")

    def _get_json(self, token: str, path: str, params: dict[str, Any] | None = None) -> Any:
        response = requests.get(
            f"{self.api_base_url}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Capacities-Api-Version": CAPACITIES_API_VERSION,
            },
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()


def _find_structure(structures: list[Any], names: list[str]) -> dict[str, Any] | None:
    wanted = {_key(name) for name in names}
    for structure in structures:
        if not isinstance(structure, dict):
            continue
        if _key(str(structure.get("title") or "")) in wanted or _key(str(structure.get("pluralName") or "")) in wanted:
            return structure
    return None


def _definition_map(structure: dict[str, Any]) -> dict[str, str]:
    definitions: dict[str, str] = {}
    for definition in structure.get("propertyDefinitions", []):
        if isinstance(definition, dict):
            definitions[_key(str(definition.get("name") or definition.get("id") or ""))] = str(definition.get("id") or "")
    return definitions


def _project_from_object(item: dict[str, Any], definitions: dict[str, str]) -> ProjectItem:
    properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    return ProjectItem(
        provider="capacities",
        id=str(item.get("id") or ""),
        title=_property_text(properties, definitions, ["title", "titulo", "nome"]) or str(item.get("title") or "Untitled project"),
        state=_property_text(properties, definitions, ["state", "status", "estado"]) or "inbox",
        area=_property_text(properties, definitions, ["area", "context", "contexto"]),
        next_action=_property_text(properties, definitions, ["next action", "next_action", "proxima acao", "próxima ação"]),
        review_at=_property_date(properties, definitions, ["review at", "review date", "revisit at", "revisitar em", "revisao", "revisão"]),
        touched_at=_property_date(properties, definitions, ["last touched", "last touch", "ultimo toque", "último toque", "last updated at", "lastUpdatedAt"])
        or _parse_datetime(item.get("lastUpdatedAt") or item.get("updatedAt")),
        importance=_property_number(properties, definitions, ["importance", "priority", "importancia", "importância", "prioridade"], 1),
        health=_property_text(properties, definitions, ["health", "saude", "saúde"]),
        priority=_property_text(properties, definitions, ["priority", "prioridade"]),
        progress=_property_number(properties, definitions, ["progress", "progresso"], 0),
        phase=_property_text(properties, definitions, ["phase", "current phase", "fase", "fase atual"]),
        url=str(item.get("url") or ""),
    )


def _property(properties: dict[str, Any], definitions: dict[str, str], names: list[str]) -> Any:
    for name in names:
        property_id = definitions.get(_key(name), name if name in properties else "")
        if property_id and property_id in properties:
            return properties[property_id]
    return None


def _property_text(properties: dict[str, Any], definitions: dict[str, str], names: list[str]) -> str:
    value = _property(properties, definitions, names)
    if not isinstance(value, dict):
        return str(value or "")
    kind = str(value.get("type") or "")
    nested = value.get(kind) if kind else None
    if isinstance(nested, dict):
        return str(nested.get("value") or nested.get("text") or nested.get("name") or "")
    if isinstance(nested, list) and nested:
        first = nested[0]
        return str(first.get("name") or first.get("value") or "") if isinstance(first, dict) else str(first)
    return str(value.get("value") or "")


def _property_date(properties: dict[str, Any], definitions: dict[str, str], names: list[str]) -> datetime | None:
    value = _property(properties, definitions, names)
    if isinstance(value, dict):
        nested = value.get("date")
        if isinstance(nested, dict):
            return _parse_datetime(nested.get("start"))
    return _parse_datetime(value)


def _property_number(properties: dict[str, Any], definitions: dict[str, str], names: list[str], default: int) -> int:
    value = _property(properties, definitions, names)
    if isinstance(value, dict):
        nested = value.get("number")
        value = nested.get("value") if isinstance(nested, dict) else nested
    try:
        return int(value)
    except (TypeError, ValueError):
        text = _property_text(properties, definitions, names).lower()
        return {"low": 1, "baixa": 1, "medium": 2, "media": 2, "média": 2, "high": 3, "alta": 3}.get(text, default)


def _parse_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(character for character in normalized if not unicodedata.combining(character))
    return " ".join(ascii_value.lower().replace("_", " ").replace("-", " ").split())


def _names(value: list[str] | tuple[str, ...] | str | None) -> list[str]:
    items = value.split(",") if isinstance(value, str) else list(value or [])
    return [str(item).strip() for item in items if str(item).strip()]
