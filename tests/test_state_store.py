from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pixel_ops.state import PixelOpsStateStore


class StateStoreTests(unittest.TestCase):
    def test_discord_people_persist_in_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PixelOpsStateStore(Path(tmp) / "pixel_ops.sqlite")

            store.upsert_discord_person("u1", "Ana", ("Ana",), last_seen_at="2026-01-01T12:00:00+00:00")
            store.upsert_discord_person("u2", "Bia", ("Bia",), last_seen_at="2026-01-02T12:00:00+00:00")

            people = store.recent_discord_people(2)

            self.assertEqual([person.user_id for person in people], ["u2", "u1"])
            self.assertEqual(store.discord_person("u1").display_name, "Ana")

    def test_pokemon_captures_are_counted_and_ordered(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PixelOpsStateStore(Path(tmp) / "pixel_ops.sqlite")
            first = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
            second = datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc)

            store.record_pokemon_capture(25, "Pikachu", "REVIEW", captured_at=first, source_provider="github", source_category="review_requested")
            store.record_pokemon_capture(25, "Pikachu", "REVIEW", captured_at=second, source_provider="github", source_category="review_requested")

            captures = store.recent_pokemon_captures(1)

            self.assertEqual(captures[0].pokemon_number, 25)
            self.assertEqual(captures[0].count, 2)
            self.assertEqual(captures[0].last_seen_at, second.isoformat())

    def test_runtime_cache_round_trips_json_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PixelOpsStateStore(Path(tmp) / "pixel_ops.sqlite")

            store.set_cache("media", "track", {"title": "Song", "plays": 3})

            self.assertEqual(store.get_cache("media", "track"), {"title": "Song", "plays": 3})

    def test_layout_profiles_round_trip_device_and_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PixelOpsStateStore(Path(tmp) / "pixel_ops.sqlite")

            profile = store.save_layout_profile(
                "thermalright-wide",
                "Thermalright wide",
                "thermalright",
                1920,
                462,
                "horizontal",
                {"game": {"x": 0, "y": 0, "width": 640, "height": 320}},
                {"output": "thermalright"},
            )

            loaded = store.layout_profile(profile.profile_id)

            self.assertEqual(loaded.width, 1920)
            self.assertEqual(loaded.layout["game"]["width"], 640)
            self.assertEqual(store.layout_profiles()[0].equipment_target, "thermalright")


if __name__ == "__main__":
    unittest.main()
