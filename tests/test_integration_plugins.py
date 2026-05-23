from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from pixel_ops.integration_plugins.base import IntegrationContext
from pixel_ops.integration_plugins.registry import build_integration_runtime
from pixel_ops.integrations.ai_usage.plugin import plugin as ai_usage_plugin
from pixel_ops.integrations.discord.plugin import plugin as discord_plugin
from pixel_ops.integrations.github.plugin import plugin as github_plugin
from pixel_ops.integrations.google_calendar.plugin import plugin as google_calendar_plugin
from pixel_ops.integrations.ics.plugin import plugin as ics_plugin
from pixel_ops.integrations.slack.plugin import plugin as slack_plugin
from pixel_ops.integrations.weather.plugin import plugin as weather_plugin


def context(config: dict, root_dir: Path | None = None, args: object | None = None) -> IntegrationContext:
    return IntegrationContext(
        root_dir=root_dir or Path.cwd(),
        args=args or argparse.Namespace(ics=None),
        config=config,
        env_bool=lambda _name, default=False: default,
        env_int=lambda _name, default=0: default,
        env_value=lambda _name, default=None: default,
        split_env_list=lambda value: [item.strip() for item in value.split(",") if item.strip()],
    )


class IntegrationPluginTests(unittest.TestCase):
    def test_plugin_factories_expose_stable_names(self):
        factories = {
            "ai_usage": ai_usage_plugin,
            "discord": discord_plugin,
            "github": github_plugin,
            "google_calendar": google_calendar_plugin,
            "ics": ics_plugin,
            "slack": slack_plugin,
            "weather": weather_plugin,
        }
        for expected_name, factory in factories.items():
            with self.subTest(plugin=expected_name):
                self.assertEqual(factory().name, expected_name)

    def test_build_integration_runtime_merges_enabled_plugins_without_starting_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ics_path = root / "calendar.ics"
            ics_path.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n", encoding="utf-8")
            cfg = {
                "integrations": {
                    "social_bus_limit": 8,
                    "slack": {"enabled": True},
                    "discord": {"enabled": True, "guild_id": "guild", "focus_user_id": "me", "max_companions": 3},
                    "github": {"enabled": True, "repos": ["owner/repo"]},
                    "google_calendar": {"enabled": True, "ics_urls": ["https://example.test/basic.ics"]},
                    "ics": {"enabled": True, "paths": [str(ics_path)]},
                    "weather": {"enabled": True, "provider": "open_meteo"},
                    "ai_usage": {"enabled": True, "providers": ["codex"], "thresholds": [80]},
                }
            }

            runtime = build_integration_runtime(context(cfg, root_dir=root))

            self.assertEqual(
                runtime.loaded_plugins,
                ["slack", "discord", "github", "google_calendar", "ics", "weather", "ai_usage"],
            )
            self.assertGreaterEqual(len(runtime.event_sources), 5)
            self.assertIn(ics_path, runtime.calendar_paths)
            self.assertIsNotNone(runtime.pull_request_source)
            self.assertIsNotNone(runtime.weather_source)
            self.assertIsNotNone(runtime.ai_usage_source)
            self.assertGreaterEqual(len(runtime.starters), 2)
            self.assertGreaterEqual(len(runtime.closers), 2)

    def test_ics_cli_argument_enables_plugin_even_when_json_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            ics_path = Path(tmp) / "calendar.ics"
            ics_path.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n", encoding="utf-8")
            args = argparse.Namespace(ics=str(ics_path))
            plugin = ics_plugin()

            contribution = plugin.build(context({"integrations": {}}, args=args))

            self.assertTrue(plugin.enabled(context({"integrations": {}}, args=args)))
            self.assertEqual(contribution.calendar_paths, [ics_path])
            self.assertEqual(len(contribution.event_sources), 1)

    def test_disabled_plugins_do_not_load(self):
        runtime = build_integration_runtime(context({"integrations": {"github": {"enabled": False}}}))

        self.assertEqual(runtime.loaded_plugins, [])
        self.assertEqual(runtime.event_sources, [])


if __name__ == "__main__":
    unittest.main()
