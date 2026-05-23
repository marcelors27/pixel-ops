from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class DiscordCompanionProfile:
    user_id: str
    display_name: str
    nicknames: tuple[str, ...] = ()
    last_seen_at: str = ""


@dataclass
class DiscordCompanionStore:
    path: Path
    max_recent: int = 50
    _profiles: dict[str, DiscordCompanionProfile] = field(default_factory=dict, init=False, repr=False)
    _loaded: bool = field(default=False, init=False, repr=False)
    _loaded_mtime: float | None = field(default=None, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def profile(self, user_id: str) -> DiscordCompanionProfile | None:
        with self._lock:
            self._load_unlocked()
            return self._profiles.get(user_id)

    def record_member(self, user_id: str, name: str) -> DiscordCompanionProfile:
        clean_id = str(user_id).strip()
        clean_name = str(name).strip() or clean_id
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._load_unlocked()
            previous = self._profiles.get(clean_id)
            nicknames = list(previous.nicknames if previous else ())
            if clean_name and clean_name not in nicknames:
                nicknames.insert(0, clean_name)
            nicknames = nicknames[:5]
            profile = DiscordCompanionProfile(
                user_id=clean_id,
                display_name=clean_name,
                nicknames=tuple(nicknames),
                last_seen_at=now,
            )
            self._profiles[clean_id] = profile
            self._trim_unlocked()
            self._save_unlocked()
            return profile

    def _load_unlocked(self) -> None:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            mtime = None
        if self._loaded and self._loaded_mtime == mtime:
            return
        self._loaded = True
        self._loaded_mtime = mtime
        self._profiles = {}
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        root = raw.get("discord_people") if isinstance(raw, dict) else {}
        if not isinstance(root, dict):
            return
        self.max_recent = _int(root.get("max_recent"), self.max_recent)
        people = root.get("people")
        if not isinstance(people, dict):
            return
        for user_id, value in people.items():
            if not isinstance(value, dict):
                continue
            profile = DiscordCompanionProfile(
                user_id=str(user_id),
                display_name=str(value.get("display_name") or user_id),
                nicknames=tuple(str(item) for item in value.get("nicknames", []) if item),
                last_seen_at=str(value.get("last_seen_at") or ""),
            )
            self._profiles[profile.user_id] = profile

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "discord_people": {
                "max_recent": self.max_recent,
                "people": {
                    user_id: {
                        "display_name": profile.display_name,
                        "nicknames": list(profile.nicknames),
                        "last_seen_at": profile.last_seen_at,
                    }
                    for user_id, profile in sorted(
                        self._profiles.items(),
                        key=lambda item: item[1].last_seen_at,
                        reverse=True,
                    )
                },
            }
        }
        self.path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")
        try:
            self._loaded_mtime = self.path.stat().st_mtime
        except OSError:
            self._loaded_mtime = None

    def _trim_unlocked(self) -> None:
        ordered = sorted(self._profiles.items(), key=lambda item: item[1].last_seen_at, reverse=True)
        self._profiles = dict(ordered[: self.max_recent])


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
