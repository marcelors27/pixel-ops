from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from pixel_ops.core import PixelOpsApp
from pixel_ops.core.screens import ScreenRotationController
from pixel_ops.plugins.spaceship.engine import SpaceshipEngine
from pixel_ops.plugins.spaceship.persistence import SpaceshipStateStore
from pixel_ops.plugins.spaceship.scene import SpaceshipScene


class SpaceshipPlugin:
    name = "spaceship"
    display_name = "Starship"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        return None

    def load_config(self, plugin_dir: Path, load_config: Callable[[Path], dict]) -> dict:
        return {"game": load_config(plugin_dir / "game.json")["game"]}

    def maybe_handle_command(self, args, root_dir: Path, config: dict) -> bool:
        return False

    def fps(self, config: dict, display_fps: int) -> int:
        return int(config["game"].get("fps", display_fps))

    def event_config(self, config: dict) -> dict:
        return config["game"].get("events", {})

    def build_app(
        self, args, root_dir: Path, display_cfg: dict, config: dict, width: int, height: int,
        fps: int, people_config: list[dict], ai_plugin, event_sources: list,
    ) -> PixelOpsApp:
        store = SpaceshipStateStore(
            root_dir / "pixel_ops/state/pixel_ops.sqlite",
            layout_seed=config["game"].get("layout_seed"),
        )
        scene = SpaceshipScene(width, height, config["game"])
        engine = SpaceshipEngine(scene, store, config["game"])
        return PixelOpsApp(engine=engine, event_sources=event_sources, screens=ScreenRotationController(display_cfg))


def plugin() -> SpaceshipPlugin:
    return SpaceshipPlugin()
