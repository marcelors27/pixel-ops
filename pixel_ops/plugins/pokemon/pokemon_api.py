from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from .pokemon import Pokemon, get_pokemon


class PokeApiClient:
    def __init__(
        self,
        cache_dir: Path,
        api_base_url: str = "https://pokeapi.co/api/v2",
        sprite_base_url: str = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon",
        timeout_seconds: int = 8,
        offline: bool = False,
        sprite_style: str = "animated",
    ):
        self.cache_dir = cache_dir
        self.api_dir = cache_dir / "api"
        self.front_dir = cache_dir / "pokemon" / "front"
        self.animated_dir = cache_dir / "pokemon" / "animated"
        self.api_base_url = api_base_url.rstrip("/")
        self.sprite_base_url = sprite_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.offline = offline
        self.sprite_style = sprite_style
        for directory in (self.api_dir, self.front_dir, self.animated_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def get(self, number: int, allow_download: bool = True) -> Pokemon:
        fallback = get_pokemon(number - 1)
        data = self._load_metadata(number, allow_download=allow_download)
        if not data:
            return fallback

        name = str(data.get("name", fallback.name)).title()
        types = tuple(slot["type"]["name"] for slot in data.get("types", []) if "type" in slot)
        front = self.ensure_sprite(number, "front", allow_download=allow_download)
        animated = self.ensure_sprite(number, "animated", allow_download=allow_download)
        return Pokemon(
            number=number,
            name=name,
            types=types,
            sprite_path=front,
            animated_sprite_path=animated,
        )

    def warm_cache(self, limit: int = 151, include_animated: bool = True) -> None:
        for number in range(1, limit + 1):
            pokemon = self.get(number, allow_download=True)
            print(f"cached #{pokemon.number:03d} {pokemon.name}")
            if include_animated:
                self.ensure_sprite(number, "animated", allow_download=True)

    def ensure_sprite(self, number: int, style: str = "front", allow_download: bool = True) -> Path | None:
        if style == "animated":
            path = self.animated_dir / f"{number:03d}.gif"
            url = f"{self.sprite_base_url}/versions/generation-v/black-white/animated/{number}.gif"
        else:
            path = self.front_dir / f"{number:03d}.png"
            url = f"{self.sprite_base_url}/{number}.png"

        if path.exists() and path.stat().st_size > 0:
            return path
        if self.offline or not allow_download:
            return None

        try:
            response = requests.get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException:
            return None

        path.write_bytes(response.content)
        return path

    def _load_metadata(self, number: int, allow_download: bool = True) -> dict[str, Any] | None:
        path = self.api_dir / f"pokemon_{number:03d}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        if self.offline or not allow_download:
            return None

        try:
            response = requests.get(f"{self.api_base_url}/pokemon/{number}", timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException:
            return None

        data = response.json()
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        return data
