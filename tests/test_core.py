from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from pixel_ops.config_loader import ConfigWatcher, load_config_prefer_json
from pixel_ops.core.app import PixelOpsApp
from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.data_sources.companions import CompanionMember, CompanionSnapshot
from pixel_ops.events.event_bus import EventBus
from pixel_ops.events.observation_sources import CallableObservationSource
from pixel_ops.events.platform import PixelOpsEvent
from pixel_ops.main import runtime_display_config, runtime_plugin_name, virtual_display_config
from pixel_ops.render.hud import hud_palette_for_kind
from pixel_ops.render.renderer import PixelRenderer


class DummyScene:
    def __init__(self):
        self.last = None

    def render(self, people_times, next_event, now, pull_requests, weather, ai_usage, pc_stats=None, task_snapshot=None, media=None, companion_snapshot=None, today_events=None):
        self.last = {
            "people_times": people_times,
            "next_event": next_event,
            "now": now,
            "pull_requests": pull_requests,
            "weather": weather,
            "ai_usage": ai_usage,
            "pc_stats": pc_stats,
            "task_snapshot": task_snapshot,
            "media": media,
            "companion_snapshot": companion_snapshot,
            "today_events": today_events,
        }
        return Image.new("RGB", (2, 2), "black")


class DummyPullRequests:
    def open_pull_requests(self, now=None):
        return [{"title": "PR"}]


class DummyWeather:
    def current(self, now):
        return {"weather": "clear"}


class DummyAiUsage:
    def current(self, now=None):
        return {"usage": "low"}


class DummyPCStats:
    def current(self, now=None):
        return {"cpu": "10%"}


class DummyTaskSource:
    def current(self, now=None):
        return {"tasks": 2}


class DummyMediaSource:
    def current(self, now=None):
        return {"title": "Track"}


class DummyCompanionSource:
    def current(self, now=None):
        return {"members": 1}


class DummySnapshotCompanionSource:
    def current(self, now=None):
        return CompanionSnapshot(members=(CompanionMember(user_id="discord:u1", name="Ana"),), group_id="discord:c1")


class CoreTests(unittest.TestCase):
    def test_event_bus_is_bounded_and_drains_in_order(self):
        bus = EventBus[str](maxlen=2)
        bus.publish("one")
        bus.publish("two")
        bus.publish("three")

        self.assertEqual(len(bus), 2)
        self.assertEqual(bus.drain(1), ["two"])
        self.assertEqual(bus.drain(), ["three"])
        self.assertEqual(len(bus), 0)

    def test_pixel_ops_app_delivers_source_events_and_tick_to_engine(self):
        class Engine:
            name = "test"

            def __init__(self):
                self.events = []

            def consume(self, event):
                self.events.append(event)

            def render(self):
                return Image.new("RGB", (2, 2), "black")

            def close(self):
                pass

        engine = Engine()
        now = datetime(2026, 1, 1, 12, 0)
        app = PixelOpsApp(
            engine=engine,
            event_sources=[CallableObservationSource("weather.conditions_updated", "weather", lambda _: {"weather": "clear"})],
        )

        frame = app.render_frame(now)

        self.assertEqual(frame.size, (2, 2))
        self.assertEqual([event.type for event in engine.events], ["weather.conditions_updated", "runtime.tick"])
        self.assertEqual(engine.events[0].payload["value"], {"weather": "clear"})
        self.assertEqual(engine.events[1].occurred_at, now)

    def test_platform_event_has_versioned_neutral_envelope(self):
        now = datetime(2026, 6, 13, 10, 15, tzinfo=ZoneInfo("America/Sao_Paulo"))
        event = PixelOpsEvent.observation("calendar.today_updated", "calendar", ["meeting"], now)

        self.assertEqual(event.type, "calendar.today_updated")
        self.assertEqual(event.source, "calendar")
        self.assertEqual(event.payload["value"], ["meeting"])
        self.assertEqual(event.schema_version, 1)
        self.assertTrue(event.id)

    def test_config_loader_prefers_json_over_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "display.yaml").write_text("value: yaml\n", encoding="utf-8")
            (root / "display.json").write_text(json.dumps({"value": "json"}), encoding="utf-8")

            self.assertEqual(load_config_prefer_json(root / "display.yaml"), {"value": "json"})

    def test_config_watcher_detects_changes_after_initial_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text('{"value": 1}\n', encoding="utf-8")
            watcher = ConfigWatcher(lambda: [path])

            self.assertFalse(watcher.changed())
            time.sleep(0.001)
            path.write_text('{"value": 2}\n', encoding="utf-8")

            self.assertTrue(watcher.changed())
            self.assertFalse(watcher.changed())

    def test_runtime_plugin_uses_studio_config(self):
        args = SimpleNamespace(plugin=None)
        self.assertEqual(runtime_plugin_name(args, {"device": {"plugin": "pokemon"}}), "pokemon")
        self.assertEqual(runtime_plugin_name(args, {"device": {"plugin": "spaceship"}}), "spaceship")

    def test_runtime_plugin_cli_override_wins(self):
        args = SimpleNamespace(plugin="spaceship")
        self.assertEqual(runtime_plugin_name(args, {"device": {"plugin": "pokemon"}}), "spaceship")

    def test_runtime_display_config_applies_horizontal_profile(self):
        args = type("Args", (), {"orientation": None})()
        display_cfg = {
            "width": 320,
            "height": 480,
            "orientation": "horizontal",
            "layout": {"game": {"width": 320}},
            "orientations": {
                "horizontal": {
                    "width": 480,
                    "height": 320,
                    "layout": {"game": {"width": 480}},
                }
            },
        }

        active = runtime_display_config(args, display_cfg)

        self.assertEqual(active["orientation"], "horizontal")
        self.assertEqual(active["width"], 480)
        self.assertEqual(active["height"], 320)
        self.assertEqual(active["layout"]["game"]["width"], 480)

    def test_runtime_display_config_cli_orientation_overrides_config(self):
        args = type("Args", (), {"orientation": "vertical"})()
        display_cfg = {
            "width": 320,
            "height": 480,
            "orientation": "horizontal",
            "orientations": {"horizontal": {"width": 480, "height": 320}},
        }

        active = runtime_display_config(args, display_cfg)

        self.assertEqual(active["orientation"], "vertical")
        self.assertEqual(active["width"], 320)
        self.assertEqual(active["height"], 480)

    def test_virtual_display_config_ignores_single_display_orientation_profile(self):
        display_cfg = {
            "width": 2650,
            "height": 462,
            "orientation": "horizontal",
            "layout": {
                "weather_forecast": {"x": 2408, "y": 8, "width": 152, "height": 40},
                "pc_stats": {"x": 100, "y": 8, "width": 152, "height": 40},
            },
            "orientations": {"horizontal": {"width": 480, "height": 320, "layout": {}}},
            "device": {
                "displays": [
                    {"enabled": True, "output": "thermalright", "x": 0, "y": 0, "width": 1920, "height": 462},
                    {"enabled": True, "output": "eink", "x": 2400, "y": 0, "width": 250, "height": 122},
                ]
            },
        }

        active = virtual_display_config(display_cfg)

        self.assertEqual((active["width"], active["height"]), (2650, 462))
        self.assertIn("weather_forecast", active["layout"])
        self.assertTrue(active["layout"]["weather_forecast"]["monochrome"])
        self.assertNotIn("monochrome", active["layout"]["pc_stats"])

    def test_hud_palettes_always_use_a_white_panel(self):
        palette = SimpleNamespace(
            panel=(216, 224, 240),
            panel_shadow=(72, 88, 112),
            ink=(16, 24, 40),
            blue=(48, 104, 184),
            red=(216, 56, 56),
            yellow=(248, 200, 48),
            green=(72, 184, 96),
        )

        themed = hud_palette_for_kind(palette, "pokemon", "weather")
        default = hud_palette_for_kind(palette, "default", "weather")
        monochrome = hud_palette_for_kind(palette, "pokemon", "weather", monochrome=True)

        self.assertEqual(themed.panel, palette.panel)
        self.assertEqual(default.panel, palette.panel)
        self.assertEqual(monochrome.panel, (255, 255, 255))
        self.assertEqual(monochrome.panel_shadow, (255, 255, 255))
        self.assertEqual(monochrome.ink, (0, 0, 0))

    def test_white_hud_panels_use_flat_monochrome_borders(self):
        image = Image.new("RGB", (20, 20), "white")

        PixelRenderer.draw_panel(
            ImageDraw.Draw(image),
            (2, 2, 10, 10),
            (255, 255, 255),
            (255, 255, 255),
            (0, 0, 0),
        )

        self.assertEqual(image.getpixel((2, 2)), (0, 0, 0))
        self.assertEqual(image.getpixel((3, 3)), (255, 255, 255))
        self.assertEqual(image.getpixel((12, 12)), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
