from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DiscordPersonRecord:
    user_id: str
    display_name: str
    nicknames: tuple[str, ...] = ()
    last_seen_at: str = ""
    guild_id: str = ""
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class PokemonCaptureRecord:
    pokemon_number: int
    pokemon_name: str
    cause: str
    captured_at: str
    last_seen_at: str
    count: int = 1
    source_provider: str = ""
    source_category: str = ""
    types: tuple[str, ...] = ()
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class LayoutProfileRecord:
    profile_id: str
    name: str
    equipment_target: str
    width: int
    height: int
    orientation: str
    layout: dict[str, Any]
    device: dict[str, Any]
    created_at: str
    updated_at: str


class PixelOpsStateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def upsert_discord_person(
        self,
        user_id: str,
        display_name: str,
        nicknames: tuple[str, ...] | list[str] = (),
        last_seen_at: str | None = None,
        guild_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DiscordPersonRecord:
        clean_id = str(user_id).strip()
        clean_name = str(display_name).strip() or clean_id
        seen_at = last_seen_at or _now_iso()
        nickname_values = tuple(str(item) for item in nicknames if item)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO discord_people (user_id, display_name, nicknames_json, last_seen_at, guild_id, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    display_name=excluded.display_name,
                    nicknames_json=excluded.nicknames_json,
                    last_seen_at=excluded.last_seen_at,
                    guild_id=excluded.guild_id,
                    metadata_json=excluded.metadata_json
                """,
                (clean_id, clean_name, _json(list(nickname_values)), seen_at, str(guild_id), _json(metadata or {})),
            )
        return DiscordPersonRecord(clean_id, clean_name, nickname_values, seen_at, str(guild_id), metadata or {})

    def discord_person(self, user_id: str) -> DiscordPersonRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_id, display_name, nicknames_json, last_seen_at, guild_id, metadata_json
                FROM discord_people
                WHERE user_id = ?
                """,
                (str(user_id),),
            ).fetchone()
        return _discord_person_from_row(row) if row else None

    def recent_discord_people(self, limit: int = 50) -> list[DiscordPersonRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, display_name, nicknames_json, last_seen_at, guild_id, metadata_json
                FROM discord_people
                ORDER BY last_seen_at DESC, user_id ASC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [_discord_person_from_row(row) for row in rows]

    def trim_discord_people(self, limit: int) -> None:
        keep = max(1, int(limit))
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM discord_people
                WHERE user_id NOT IN (
                    SELECT user_id FROM discord_people
                    ORDER BY last_seen_at DESC, user_id ASC
                    LIMIT ?
                )
                """,
                (keep,),
            )

    def record_pokemon_capture(
        self,
        pokemon_number: int,
        pokemon_name: str,
        cause: str,
        captured_at: datetime | str | None = None,
        source_provider: str = "",
        source_category: str = "",
        types: tuple[str, ...] | list[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> PokemonCaptureRecord:
        captured_iso = _datetime_iso(captured_at)
        clean_name = str(pokemon_name).strip() or f"Pokemon #{int(pokemon_number):03d}"
        clean_cause = str(cause).strip() or "AMBIENT"
        type_values = tuple(str(item) for item in types if item)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pokemon_captures (
                    pokemon_number, pokemon_name, cause, captured_at, last_seen_at, count,
                    source_provider, source_category, types_json, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(pokemon_number, cause, source_provider, source_category) DO UPDATE SET
                    pokemon_name=excluded.pokemon_name,
                    last_seen_at=excluded.last_seen_at,
                    count=count + 1,
                    types_json=excluded.types_json,
                    metadata_json=excluded.metadata_json
                """,
                (
                    int(pokemon_number),
                    clean_name,
                    clean_cause,
                    captured_iso,
                    captured_iso,
                    str(source_provider),
                    str(source_category),
                    _json(list(type_values)),
                    _json(metadata or {}),
                ),
            )
        return PokemonCaptureRecord(
            int(pokemon_number),
            clean_name,
            clean_cause,
            captured_iso,
            captured_iso,
            1,
            str(source_provider),
            str(source_category),
            type_values,
            metadata or {},
        )

    def recent_pokemon_captures(self, limit: int = 10) -> list[PokemonCaptureRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT pokemon_number, pokemon_name, cause, captured_at, last_seen_at, count,
                       source_provider, source_category, types_json, metadata_json
                FROM pokemon_captures
                ORDER BY last_seen_at DESC, pokemon_number ASC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [_pokemon_capture_from_row(row) for row in rows]

    def set_cache(
        self,
        namespace: str,
        key: str,
        value: Any,
        expires_at: datetime | str | None = None,
    ) -> None:
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runtime_cache (namespace, key, value_json, created_at, updated_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(namespace, key) DO UPDATE SET
                    value_json=excluded.value_json,
                    updated_at=excluded.updated_at,
                    expires_at=excluded.expires_at
                """,
                (str(namespace), str(key), _json(value), now, now, _datetime_iso(expires_at) if expires_at else None),
            )

    def get_cache(self, namespace: str, key: str) -> Any | None:
        now = _now_iso()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT value_json, expires_at
                FROM runtime_cache
                WHERE namespace = ? AND key = ?
                """,
                (str(namespace), str(key)),
            ).fetchone()
            if not row:
                return None
            if row["expires_at"] and row["expires_at"] < now:
                conn.execute("DELETE FROM runtime_cache WHERE namespace = ? AND key = ?", (str(namespace), str(key)))
                return None
        return _loads(row["value_json"], None)

    def save_layout_profile(
        self,
        profile_id: str,
        name: str,
        equipment_target: str,
        width: int,
        height: int,
        orientation: str,
        layout: dict[str, Any],
        device: dict[str, Any] | None = None,
    ) -> LayoutProfileRecord:
        now = _now_iso()
        clean_id = str(profile_id).strip()
        with self._connect() as conn:
            existing = conn.execute("SELECT created_at FROM layout_profiles WHERE id = ?", (clean_id,)).fetchone()
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT INTO layout_profiles (
                    id, name, equipment_target, width, height, orientation,
                    layout_json, device_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    equipment_target=excluded.equipment_target,
                    width=excluded.width,
                    height=excluded.height,
                    orientation=excluded.orientation,
                    layout_json=excluded.layout_json,
                    device_json=excluded.device_json,
                    updated_at=excluded.updated_at
                """,
                (
                    clean_id,
                    str(name),
                    str(equipment_target),
                    int(width),
                    int(height),
                    str(orientation),
                    _json(layout),
                    _json(device or {}),
                    created_at,
                    now,
                ),
            )
        return LayoutProfileRecord(clean_id, str(name), str(equipment_target), int(width), int(height), str(orientation), layout, device or {}, created_at, now)

    def layout_profiles(self) -> list[LayoutProfileRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, equipment_target, width, height, orientation,
                       layout_json, device_json, created_at, updated_at
                FROM layout_profiles
                ORDER BY updated_at DESC, name ASC
                """
            ).fetchall()
        return [_layout_profile_from_row(row) for row in rows]

    def layout_profile(self, profile_id: str) -> LayoutProfileRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, name, equipment_target, width, height, orientation,
                       layout_json, device_json, created_at, updated_at
                FROM layout_profiles
                WHERE id = ?
                """,
                (str(profile_id),),
            ).fetchone()
        return _layout_profile_from_row(row) if row else None

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS discord_people (
                    user_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    nicknames_json TEXT NOT NULL DEFAULT '[]',
                    last_seen_at TEXT NOT NULL,
                    guild_id TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS pokemon_captures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pokemon_number INTEGER NOT NULL,
                    pokemon_name TEXT NOT NULL,
                    cause TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 1,
                    source_provider TEXT NOT NULL DEFAULT '',
                    source_category TEXT NOT NULL DEFAULT '',
                    types_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(pokemon_number, cause, source_provider, source_category)
                );

                CREATE TABLE IF NOT EXISTS runtime_cache (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT,
                    PRIMARY KEY(namespace, key)
                );

                CREATE TABLE IF NOT EXISTS layout_profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    equipment_target TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    orientation TEXT NOT NULL,
                    layout_json TEXT NOT NULL,
                    device_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _datetime_iso(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if value:
        return str(value)
    return _now_iso()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _loads(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback


def _discord_person_from_row(row: sqlite3.Row) -> DiscordPersonRecord:
    nicknames = _loads(row["nicknames_json"], [])
    metadata = _loads(row["metadata_json"], {})
    return DiscordPersonRecord(
        user_id=str(row["user_id"]),
        display_name=str(row["display_name"]),
        nicknames=tuple(str(item) for item in nicknames if item),
        last_seen_at=str(row["last_seen_at"]),
        guild_id=str(row["guild_id"]),
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def _pokemon_capture_from_row(row: sqlite3.Row) -> PokemonCaptureRecord:
    types = _loads(row["types_json"], [])
    metadata = _loads(row["metadata_json"], {})
    return PokemonCaptureRecord(
        pokemon_number=int(row["pokemon_number"]),
        pokemon_name=str(row["pokemon_name"]),
        cause=str(row["cause"]),
        captured_at=str(row["captured_at"]),
        last_seen_at=str(row["last_seen_at"]),
        count=int(row["count"]),
        source_provider=str(row["source_provider"]),
        source_category=str(row["source_category"]),
        types=tuple(str(item) for item in types if item),
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def _layout_profile_from_row(row: sqlite3.Row) -> LayoutProfileRecord:
    layout = _loads(row["layout_json"], {})
    device = _loads(row["device_json"], {})
    return LayoutProfileRecord(
        profile_id=str(row["id"]),
        name=str(row["name"]),
        equipment_target=str(row["equipment_target"]),
        width=int(row["width"]),
        height=int(row["height"]),
        orientation=str(row["orientation"]),
        layout=layout if isinstance(layout, dict) else {},
        device=device if isinstance(device, dict) else {},
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
