from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from PIL import Image

from pixel_ops.config_loader import ConfigWatcher, load_config_prefer_json
from pixel_ops.core.app import PixelOpsApp
from pixel_ops.events.event_bus import EventBus
from pixel_ops.main import runtime_display_config


class DummyScene:
    def __init__(self):
        self.last = None

    def render(self, people_times, next_event, now, pull_requests, weather, ai_usage, pc_stats=None, task_snapshot=None):
        self.last = {
            "people_times": people_times,
            "next_event": next_event,
            "now": now,
            "pull_requests": pull_requests,
            "weather": weather,
            "ai_usage": ai_usage,
            "pc_stats": pc_stats,
            "task_snapshot": task_snapshot,
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

    def test_pixel_ops_app_passes_built_runtime_state_to_scene(self):
        scene = DummyScene()
        now = datetime(2026, 1, 1, 12, 0)
        app = PixelOpsApp(
            scene=scene,
            people_config=[
                {
                    "key": "BRT",
                    "name": "Team",
                    "country": "BR",
                    "timezone": "America/Sao_Paulo",
                    "timezone_label": "Brazil",
                    "work_start": "09:00",
                    "work_end": "18:00",
                }
            ],
            next_event=lambda _: "meeting",
            pull_request_source=DummyPullRequests(),
            weather_source=DummyWeather(),
            ai_usage_source=DummyAiUsage(),
            pc_stats_source=DummyPCStats(),
            task_source=DummyTaskSource(),
        )

        frame = app.render_frame(now)

        self.assertEqual(frame.size, (2, 2))
        self.assertEqual(scene.last["next_event"], "meeting")
        self.assertEqual(scene.last["pull_requests"], [{"title": "PR"}])
        self.assertEqual(scene.last["weather"], {"weather": "clear"})
        self.assertEqual(scene.last["ai_usage"], {"usage": "low"})
        self.assertEqual(scene.last["pc_stats"], {"cpu": "10%"})
        self.assertEqual(scene.last["task_snapshot"], {"tasks": 2})
        self.assertEqual(scene.last["people_times"][0].timezone, "America/Sao_Paulo")

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


if __name__ == "__main__":
    unittest.main()
