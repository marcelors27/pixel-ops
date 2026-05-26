from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pixel_ops.core import AIUsageSource, PCStatsSource, PixelOpsApp, PullRequestSource, WeatherSource
from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.events.base import EventSource
from pixel_ops.plugins.ai.plugin import AiDecisionPlugin
from pixel_ops.plugins.pokemon.pokemon_api import PokeApiClient
from pixel_ops.plugins.pokemon.scenes.overworld_scene import OverworldScene


class PokemonPlugin:
    name = "pokemon"
    display_name = "Pokemon"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--offline", action="store_true", help="Use only cached Pokemon API data/sprites.")
        parser.add_argument("--warm-cache", action="store_true", help="Download/cache Gen 1 Pokemon metadata and sprites.")
        parser.add_argument("--pokemon-limit", type=int, default=151)

    def load_config(self, plugin_dir: Path, load_config: Callable[[Path], dict]) -> dict:
        companions_path = plugin_dir / "companions.json"
        return {
            "game": load_config(plugin_dir / "game.json")["game"],
            "pokemon": load_config(plugin_dir / "pokemon.json")["pokemon"],
            "companions": load_config(companions_path).get("companions", {}) if companions_path.exists() else {},
        }

    def maybe_handle_command(self, args: argparse.Namespace, root_dir: Path, config: dict) -> bool:
        if not args.warm_cache:
            return False
        pokemon_cfg = config["pokemon"]
        pokemon_api = self._pokemon_api(args, root_dir, pokemon_cfg)
        pokemon_api.warm_cache(limit=args.pokemon_limit, include_animated=True)
        return True

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
        pull_request_source: PullRequestSource,
        weather_source: WeatherSource | None,
        ai_usage_source: AIUsageSource | None,
        pc_stats_source: PCStatsSource | None,
        ai_plugin: AiDecisionPlugin | None,
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
            lazy_download=bool(pokemon_cfg.get("lazy_download", True)) and not self._offline(args, pokemon_cfg),
            scene_fps=fps,
            game_config=config["game"],
            companion_config=config.get("companions", {}),
            display_layout=display_cfg.get("layout", {}),
            event_sources=event_sources,
            ai_plugin=ai_plugin,
        )
        return PixelOpsApp(
            scene=scene,
            people_config=people_config,
            next_event=next_event,
            pull_request_source=pull_request_source,
            weather_source=weather_source,
            ai_usage_source=ai_usage_source,
            pc_stats_source=pc_stats_source,
        )

    def _pokemon_api(self, args: argparse.Namespace, root_dir: Path, pokemon_cfg: dict) -> PokeApiClient:
        return PokeApiClient(
            cache_dir=root_dir / pokemon_cfg["cache_dir"],
            api_base_url=pokemon_cfg["api_base_url"],
            sprite_base_url=pokemon_cfg["sprite_base_url"],
            timeout_seconds=int(pokemon_cfg.get("network_timeout_seconds", 8)),
            offline=self._offline(args, pokemon_cfg),
            sprite_style=pokemon_cfg.get("sprite_style", "animated"),
        )

    @staticmethod
    def _offline(args: argparse.Namespace, pokemon_cfg: dict) -> bool:
        return bool(args.offline or pokemon_cfg.get("offline", False))
