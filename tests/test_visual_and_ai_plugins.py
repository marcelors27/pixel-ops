from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from pixel_ops.data_sources.weather import OpenMeteoWeatherSource, OpenWeatherMapWeatherSource, WttrInWeatherSource, build_weather_source
from pixel_ops.plugins.ai.plugin import OpenAiChatGptPlugin, build_ai_plugin
from pixel_ops.plugins.pokemon.plugin import PokemonPlugin
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


if __name__ == "__main__":
    unittest.main()
