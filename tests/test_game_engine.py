from __future__ import annotations

import unittest
from datetime import datetime

from PIL import Image

from pixel_ops.events.base import EventCategory, WorkEvent
from pixel_ops.events.platform import PixelOpsEvent
from pixel_ops.plugins.pokemon.engine import PokemonEngine


class RecordingEncounters:
    def __init__(self):
        self.events = []

    def enqueue(self, event):
        self.events.append(event)


class RecordingScene:
    def __init__(self):
        self.encounter_system = RecordingEncounters()
        self.last_args = None
        self.last_kwargs = None

    def render(self, *args, **kwargs):
        self.last_args = args
        self.last_kwargs = kwargs
        return Image.new("RGB", (3, 2), "black")


class PokemonEngineTests(unittest.TestCase):
    def test_observations_are_projected_inside_pokemon_engine(self):
        scene = RecordingScene()
        engine = PokemonEngine(scene, people_config=[])
        now = datetime(2026, 8, 2, 12, 0)
        observations = {
            "calendar.next_updated": "planning",
            "calendar.today_updated": [],
            "github.pull_requests_updated": ["pr-1"],
            "weather.conditions_updated": "clear",
            "ai.usage_updated": "low",
            "system.metrics_updated": "healthy",
            "tasks.snapshot_updated": "tasks",
            "media.playback_updated": "track",
        }
        for event_type, value in observations.items():
            engine.consume(PixelOpsEvent.observation(event_type, "test", value, now))
        engine.consume(PixelOpsEvent.tick(now))

        frame = engine.render()

        self.assertEqual(frame.size, (3, 2))
        self.assertEqual(scene.last_args[1:6], ("planning", now, ["pr-1"], "clear", "low"))
        self.assertEqual(scene.last_kwargs["pc_stats"], "healthy")
        self.assertEqual(scene.last_kwargs["task_snapshot"], "tasks")
        self.assertEqual(scene.last_kwargs["media"], "track")

    def test_work_events_enter_pokemon_encounter_queue(self):
        scene = RecordingScene()
        engine = PokemonEngine(scene, people_config=[])
        event = WorkEvent(category=EventCategory.MERGE, title="Merged", source="github")

        engine.consume(event)

        self.assertEqual(scene.encounter_system.events, [event])


if __name__ == "__main__":
    unittest.main()
