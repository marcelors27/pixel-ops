from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pixel_ops.core import PixelOpsApp
from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.events.base import EventSource
from pixel_ops.events.github_events import GitHubEventSource
from pixel_ops.plugins.pokemon.pokemon_api import PokeApiClient
from pixel_ops.plugins.pokemon.scenes.overworld_scene import OverworldScene


class PokemonPlugin:
    name = "pokemon"
    display_name = "Pokemon"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--offline", action="store_true", help="Use only cached Pokemon API data/sprites.")
        parser.add_argument("--warm-cache", action="store_true", help="Download/cache Gen 1 Pokemon metadata and sprites.")
        parser.add_argument("--pokemon-limit", type=int, default=151)

    def load_config(self, plugin_dir: Path, load_yaml: Callable[[Path], dict]) -> dict:
        return {
            "game": load_yaml(plugin_dir / "game.yaml")["game"],
            "pokemon": load_yaml(plugin_dir / "pokemon.yaml")["pokemon"],
        }

    def maybe_handle_command(self, args: argparse.Namespace, root_dir: Path, config: dict) -> bool:
        pokemon_cfg = config["pokemon"]
        pokemon_api = self._pokemon_api(args, root_dir, pokemon_cfg)
        if args.warm_cache:
            pokemon_api.warm_cache(limit=args.pokemon_limit, include_animated=True)
            return True
        return False

    def fps(self, config: dict, display_fps: int) -> int:
        return int(config["game"].get("fps", display_fps))

    def event_config(self, config: dict) -> dict:
        return config["game"].get("events", {})

    def build_app(
        self,
        args: argparse.Namespace,
        root_dir: Path,
        display_cfg: dict,
        config: dict,
        width: int,
        height: int,
        fps: int,
        people_config: list[dict],
        next_event: Callable[[datetime], CalendarEvent | None],
        github_source: GitHubEventSource,
        event_sources: list[EventSource],
    ) -> PixelOpsApp:
        pokemon_cfg = config["pokemon"]
        pokemon_api = self._pokemon_api(args, root_dir, pokemon_cfg)
        scene = OverworldScene(
            width,
            height,
            display_cfg["timezone_primary"],
            scanlines=bool(display_cfg.get("scanlines", True)),
            pokemon_api=pokemon_api,
            lazy_download=bool(pokemon_cfg.get("lazy_download", True)) and not args.offline,
            scene_fps=fps,
            game_config=config["game"],
            event_sources=event_sources,
        )
        return PixelOpsApp(
            scene=scene,
            people_config=people_config,
            next_event=next_event,
            github_source=github_source,
        )

    def _pokemon_api(self, args: argparse.Namespace, root_dir: Path, pokemon_cfg: dict) -> PokeApiClient:
        return PokeApiClient(
            cache_dir=root_dir / pokemon_cfg["cache_dir"],
            api_base_url=pokemon_cfg["api_base_url"],
            sprite_base_url=pokemon_cfg["sprite_base_url"],
            timeout_seconds=int(pokemon_cfg.get("network_timeout_seconds", 8)),
            offline=args.offline,
            sprite_style=pokemon_cfg.get("sprite_style", "animated"),
        )
