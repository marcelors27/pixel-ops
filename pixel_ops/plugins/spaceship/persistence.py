from __future__ import annotations

import sqlite3
import secrets
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class ShipProfile:
    profile_id: str
    ship_name: str
    created_at: str
    total_active_seconds: float
    distance_travelled: float
    reactor_energy: float
    ship_level: int
    current_sector: int
    layout_seed: int


@dataclass(frozen=True)
class AsteroidRecord:
    pr_key: str
    repo: str
    number: int
    material_type: str
    processing_state: str
    discovered_at: str
    updated_at: str


class SpaceshipStateStore:
    """Plugin-owned durable state with transactional event receipts."""

    def __init__(self, path: str | Path, profile_id: str = "default", layout_seed: int | str | None = None):
        self.path = Path(path)
        self.profile_id = profile_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self._ensure_profile(layout_seed)

    def profile(self) -> ShipProfile:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM spaceship_profiles WHERE id = ?", (self.profile_id,)).fetchone()
        if row is None:
            raise RuntimeError(f"Missing spaceship profile {self.profile_id}")
        return _profile(row)

    def advance_time(self, active_seconds: float, distance_rate: float, energy_rate: float, now: datetime) -> ShipProfile:
        seconds = max(0.0, float(active_seconds))
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE spaceship_profiles
                SET total_active_seconds = total_active_seconds + ?,
                    distance_travelled = distance_travelled + ?,
                    reactor_energy = reactor_energy + ?,
                    ship_level = 1 + CAST((distance_travelled + ?) / 1000 AS INTEGER),
                    current_sector = 1 + CAST((distance_travelled + ?) / 2500 AS INTEGER),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    seconds,
                    seconds * distance_rate,
                    seconds * energy_rate,
                    seconds * distance_rate,
                    seconds * distance_rate,
                    now.isoformat(),
                    self.profile_id,
                ),
            )
        return self.profile()

    def discover_asteroid(self, pr_key: str, repo: str, number: int, material_type: str, state: str, now: datetime) -> bool:
        timestamp = now.isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO spaceship_asteroids (
                    profile_id, pr_key, repo, pr_number, material_type,
                    processing_state, discovered_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (self.profile_id, pr_key, repo, int(number), material_type, state, timestamp, timestamp),
            )
            created = cursor.rowcount > 0
            if created:
                self._add_resource(conn, "raw_ore", 1)
            else:
                conn.execute(
                    """UPDATE spaceship_asteroids
                       SET processing_state = CASE
                               WHEN processing_state IN ('refined', 'abandoned') THEN processing_state
                               ELSE ?
                           END,
                           updated_at = ?
                       WHERE profile_id = ? AND pr_key = ?""",
                    (state, timestamp, self.profile_id, pr_key),
                )
        return created

    def apply_event(self, event_key: str, pr_key: str, state: str, resource: str | None, now: datetime) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO spaceship_event_receipts
                   (profile_id, event_key, event_type, processed_at)
                   VALUES (?, ?, ?, ?)""",
                (self.profile_id, event_key, state, now.isoformat()),
            )
            if cursor.rowcount == 0:
                return False
            conn.execute(
                """UPDATE spaceship_asteroids
                   SET processing_state = ?, updated_at = ?
                   WHERE profile_id = ? AND pr_key = ?""",
                (state, now.isoformat(), self.profile_id, pr_key),
            )
            if resource:
                self._add_resource(conn, resource, 1)
        return True

    def asteroids(self, limit: int = 12) -> list[AsteroidRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT pr_key, repo, pr_number, material_type, processing_state, discovered_at, updated_at
                   FROM spaceship_asteroids WHERE profile_id = ?
                   ORDER BY updated_at DESC LIMIT ?""",
                (self.profile_id, max(1, int(limit))),
            ).fetchall()
        return [
            AsteroidRecord(
                pr_key=str(row["pr_key"]), repo=str(row["repo"]), number=int(row["pr_number"]),
                material_type=str(row["material_type"]), processing_state=str(row["processing_state"]),
                discovered_at=str(row["discovered_at"]), updated_at=str(row["updated_at"]),
            )
            for row in rows
        ]

    def resources(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT resource, amount FROM spaceship_resources WHERE profile_id = ?",
                (self.profile_id,),
            ).fetchall()
        return {str(row["resource"]): int(row["amount"]) for row in rows}

    def receipt_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM spaceship_event_receipts WHERE profile_id = ?",
                (self.profile_id,),
            ).fetchone()
        return int(row["count"] if row else 0)

    def _add_resource(self, conn: sqlite3.Connection, resource: str, amount: int) -> None:
        conn.execute(
            """INSERT INTO spaceship_resources (profile_id, resource, amount)
               VALUES (?, ?, ?)
               ON CONFLICT(profile_id, resource) DO UPDATE SET amount = amount + excluded.amount""",
            (self.profile_id, resource, int(amount)),
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_profile(self, layout_seed: int | str | None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        generated_seed = _normalize_layout_seed(layout_seed)
        if generated_seed is None:
            generated_seed = secrets.randbelow(2_147_483_647)
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO spaceship_profiles
                   (id, ship_name, created_at, updated_at, layout_seed)
                   VALUES (?, ?, ?, ?, ?)""",
                (self.profile_id, "PXS Wayfarer", now, now, generated_seed),
            )
            if layout_seed is not None:
                conn.execute(
                    "UPDATE spaceship_profiles SET layout_seed = ?, updated_at = ? WHERE id = ?",
                    (generated_seed, now, self.profile_id),
                )

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS spaceship_profiles (
                    id TEXT PRIMARY KEY,
                    ship_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    total_active_seconds REAL NOT NULL DEFAULT 0,
                    distance_travelled REAL NOT NULL DEFAULT 0,
                    reactor_energy REAL NOT NULL DEFAULT 0,
                    ship_level INTEGER NOT NULL DEFAULT 1,
                    current_sector INTEGER NOT NULL DEFAULT 1,
                    layout_seed INTEGER,
                    schema_version INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS spaceship_resources (
                    profile_id TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    amount INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(profile_id, resource),
                    FOREIGN KEY(profile_id) REFERENCES spaceship_profiles(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS spaceship_asteroids (
                    profile_id TEXT NOT NULL,
                    pr_key TEXT NOT NULL,
                    repo TEXT NOT NULL,
                    pr_number INTEGER NOT NULL,
                    material_type TEXT NOT NULL,
                    processing_state TEXT NOT NULL,
                    discovered_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(profile_id, pr_key),
                    FOREIGN KEY(profile_id) REFERENCES spaceship_profiles(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS spaceship_event_receipts (
                    profile_id TEXT NOT NULL,
                    event_key TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    PRIMARY KEY(profile_id, event_key),
                    FOREIGN KEY(profile_id) REFERENCES spaceship_profiles(id) ON DELETE CASCADE
                );
                """
            )
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(spaceship_profiles)")}
            if "layout_seed" not in columns:
                conn.execute("ALTER TABLE spaceship_profiles ADD COLUMN layout_seed INTEGER")
            conn.execute(
                "UPDATE spaceship_profiles SET layout_seed = abs(random()) % 2147483647 WHERE layout_seed IS NULL"
            )


def _profile(row: sqlite3.Row) -> ShipProfile:
    return ShipProfile(
        profile_id=str(row["id"]), ship_name=str(row["ship_name"]), created_at=str(row["created_at"]),
        total_active_seconds=float(row["total_active_seconds"]), distance_travelled=float(row["distance_travelled"]),
        reactor_energy=float(row["reactor_energy"]), ship_level=int(row["ship_level"]),
        current_sector=int(row["current_sector"]), layout_seed=int(row["layout_seed"]),
    )


def _normalize_layout_seed(value: int | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value % 2_147_483_647
    text = str(value).strip()
    if text.lstrip("-").isdigit():
        return int(text) % 2_147_483_647
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:4], "big") % 2_147_483_647
