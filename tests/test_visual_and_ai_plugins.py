from __future__ import annotations

import argparse
import json
import random
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

from pixel_ops.data_sources.weather import OpenMeteoWeatherSource, OpenWeatherMapWeatherSource, WttrInWeatherSource, build_weather_source
from pixel_ops.integrations.discord.voice_state import DiscordVoiceMember, DiscordVoiceSnapshot
from pixel_ops.plugins.ai.plugin import OpenAiChatGptPlugin, build_ai_plugin
from pixel_ops.plugins.pokemon.game.map_routes import MapArea, MapRouteManager
from pixel_ops.plugins.pokemon.plugin import PokemonPlugin
from pixel_ops.plugins.pokemon.scenes.overworld_scene import OverworldScene
from pixel_ops.plugins.registry import available_plugins, get_plugin


class VisualAndAiPluginTests(unittest.TestCase):
    def test_visual_plugin_registry_exposes_pokemon(self):
        plugins = available_plugins()

        self.assertIn("pokemon", plugins)
        self.assertIs(get_plugin("pokemon").__class__, PokemonPlugin)
        with self.assertRaises(ValueError):
            get_plugin("missing")

    def test_pokemon_plugin_loads_required_and_optional_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp)
            (plugin_dir / "game.json").write_text(json.dumps({"game": {"fps": 12, "events": {"queue_limit": 3}}}), encoding="utf-8")
            (plugin_dir / "pokemon.json").write_text(json.dumps({"pokemon": {"offline": True, "cache_dir": "cache"}}), encoding="utf-8")
            (plugin_dir / "companions.json").write_text(json.dumps({"companions": {"discord": {"u1": {"sprite_variant": 2}}}}), encoding="utf-8")

            cfg = PokemonPlugin().load_config(plugin_dir, lambda path: json.loads(path.read_text(encoding="utf-8")))

            self.assertEqual(cfg["game"]["fps"], 12)
            self.assertTrue(cfg["pokemon"]["offline"])
            self.assertEqual(cfg["companions"]["discord"]["u1"]["sprite_variant"], 2)
            self.assertEqual(PokemonPlugin().fps(cfg, 10), 12)
            self.assertEqual(PokemonPlugin().event_config(cfg), {"queue_limit": 3})

    def test_pokemon_plugin_one_shot_command_returns_false_when_not_requested(self):
        plugin = PokemonPlugin()
        args = argparse.Namespace(warm_cache=False, offline=True, pokemon_limit=1)

        handled = plugin.maybe_handle_command(args, Path.cwd(), {"pokemon": {"offline": True, "cache_dir": "pixel_ops/cache"}})

        self.assertFalse(handled)

    def test_ai_plugin_factory_and_disabled_decision(self):
        plugin = build_ai_plugin({"provider": "openai_chatgpt", "enabled": False})

        self.assertIsInstance(plugin, OpenAiChatGptPlugin)
        self.assertFalse(plugin.enabled)
        self.assertIsNone(plugin.decide_json(None))  # Disabled plugin returns before reading the request.
        self.assertIsNone(build_ai_plugin({"provider": "unknown"}))

    def test_weather_source_factory_supports_all_configured_providers(self):
        self.assertIsInstance(build_weather_source("open_meteo"), OpenMeteoWeatherSource)
        self.assertIsInstance(build_weather_source("wttr_in"), WttrInWeatherSource)
        self.assertIsInstance(build_weather_source("openweathermap"), OpenWeatherMapWeatherSource)
        with self.assertRaises(ValueError):
            build_weather_source("unsupported")

    def test_pokemon_scene_renders_live_screen_beside_discord_streamer(self):
        snapshot = DiscordVoiceSnapshot(
            channel_id="c1",
            members=(
                DiscordVoiceMember("u1", "Ana", "c1"),
                DiscordVoiceMember("u2", "Bia", "c1"),
            ),
            active_stream_user_ids=("u1",),
        )
        source = type("DiscordSource", (), {"discord_voice_snapshot": lambda self: snapshot})()
        scene = OverworldScene(
            320,
            240,
            "America/Sao_Paulo",
            scanlines=False,
            pokemon_api=None,
            lazy_download=False,
            game_config={"hud_height": 72, "text_box_height": 76},
            event_sources=[source],
        )

        img = scene.render_full([], None, datetime.now(ZoneInfo("America/Sao_Paulo")))

        self.assertEqual(img.size, (320, 240))
        self.assertEqual(len(scene._voice_companions), 2)
        streamer_state = scene._voice_companions["u1"]
        self.assertEqual(streamer_state.direction, "down")
        self.assertEqual(streamer_state.x, streamer_state.target_x)
        self.assertEqual(streamer_state.y, streamer_state.target_y)
        live_screen = scene._live_screen_sprite()
        live_layers = [
            layer
            for layer in scene._sprite_layers(scene.state.phase)
            if layer[0].size == live_screen.size and not layer[3]
        ]
        self.assertEqual(len(live_layers), 1)
        scene.frame += max(1, scene.scene_fps // 4)
        self.assertNotEqual(scene._live_screen_sprite().tobytes(), live_screen.tobytes())

    def test_pokemon_scene_uses_source_map_movement_rects_for_companions(self):
        scene = OverworldScene(
            320,
            240,
            "America/Sao_Paulo",
            scanlines=False,
            pokemon_api=None,
            lazy_download=False,
            game_config={
                "hud_height": 72,
                "text_box_height": 76,
                "movement": {
                    "walkable": {
                        "source_rects": [{"map": "town", "x": 100, "y": 80, "w": 70, "h": 50}],
                        "avoid_source_rects": [],
                    }
                },
            },
        )
        scene.current_map_area = MapArea(
            area_id="town:0",
            source_path=Path("town.png"),
            map_key="town",
            crop_box=(80, 60, 240, 160),
            source_bounds=(0, 0, 320, 240),
            route=((0, 0), (1, 1)),
        )

        x, y = scene._random_companion_target(random.Random(3), 20, 20)

        self.assertGreaterEqual(x, scene.map_box[0] + 100)
        self.assertLessEqual(x, scene.map_box[0] + 150)
        self.assertGreaterEqual(y, scene.map_box[1] + 20)
        self.assertLessEqual(y, scene.map_box[1] + 50)

    def test_pokemon_scene_keeps_first_companion_inside_walkable_area(self):
        scene = OverworldScene(
            320,
            240,
            "America/Sao_Paulo",
            scanlines=False,
            pokemon_api=None,
            lazy_download=False,
            game_config={
                "hud_height": 72,
                "text_box_height": 76,
                "movement": {
                    "walkable": {
                        "source_rects": [{"map": "town", "x": 40, "y": 40, "w": 180, "h": 80}],
                    }
                },
            },
        )
        scene.current_map_area = MapArea(
            area_id="town:0",
            source_path=Path("town.png"),
            map_key="town",
            crop_box=(0, 0, 320, 160),
            source_bounds=(0, 0, 320, 160),
            route=((0, 0), (1, 1)),
        )

        state = scene._voice_companion_state("u1", 123, ash_x=300, ash_y=10, sprite_variant=None)
        sprite = scene.npc_sprites.frame(state.variant, "idle_down", scene.frame)

        self.assertIsNotNone(
            scene._sprite_movement_rect(
                "companions",
                int(round(state.x)),
                int(round(state.y)),
                sprite.width,
                sprite.height,
            )
        )

    def test_pokemon_scene_limits_routes_to_maps_with_walkable_areas(self):
        scene = OverworldScene(
            320,
            240,
            "America/Sao_Paulo",
            scanlines=False,
            pokemon_api=None,
            lazy_download=False,
            game_config={
                "hud_height": 72,
                "text_box_height": 76,
                "movement": {
                    "walkable": {
                        "source_rects": [
                            {"map": "town", "x": 100, "y": 80, "w": 70, "h": 50},
                            {"map_id": "cave", "x": 24, "y": 32, "w": 40, "h": 40},
                        ],
                    },
                    "blocked": {"source_rects": [{"map": "ignored", "x": 0, "y": 0, "w": 20, "h": 20}]},
                },
            },
        )

        self.assertEqual(scene._configured_walkable_map_keys(), {"town", "cave"})
        self.assertEqual(scene.map_routes.allowed_map_keys, {"town", "cave"})
        self.assertEqual(
            scene.map_routes.walkable_source_rects["town"],
            ((100, 80, 170, 130),),
        )

    def test_map_route_manager_skips_maps_without_walkable_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            maps_dir = Path(tmp)
            (maps_dir / "ignored.png").touch()
            manager = MapRouteManager(maps_dir, (160, 120), allowed_map_keys={"allowed"})

            self.assertEqual(manager.areas, [])

    def test_map_route_manager_can_route_from_walkable_rects(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = MapRouteManager(
                Path(tmp),
                (160, 120),
                walkable_source_rects={"town": [(20, 30, 120, 70)]},
            )

            route = manager._route_for_source_rects("town", (0, 0, 160, 120))

            self.assertEqual(len(route), 2)
            self.assertGreater(route[1][0], route[0][0])
            self.assertEqual(route[0][1], route[1][1])

    def test_map_route_manager_requires_walkable_coverage_for_loaded_areas(self):
        with tempfile.TemporaryDirectory() as tmp:
            maps_dir = Path(tmp)
            Image.new("RGB", (200, 100), (64, 150, 86)).save(maps_dir / "allowed.png")
            manager = MapRouteManager(
                maps_dir,
                (100, 100),
                walkable_source_rects={"allowed": [(0, 0, 100, 70), (140, 0, 160, 20)]},
                min_walkable_coverage=0.6,
            )

            self.assertGreater(len(manager.areas), 0)
            self.assertTrue(
                all(manager._walkable_coverage(area.map_key, area.crop_box) >= 0.6 for area in manager.areas)
            )


if __name__ == "__main__":
    unittest.main()
