from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from pixel_ops.events.base import EventCategory, WorkEvent
from pixel_ops.events.github_events import PullRequestSummary
from pixel_ops.events.platform import PixelOpsEvent
from pixel_ops.plugins.spaceship.engine import SpaceshipEngine, material_for_pr
from pixel_ops.plugins.spaceship.persistence import AsteroidRecord, SpaceshipStateStore
from pixel_ops.plugins.spaceship.scene import (
    _active_mining_asteroid,
    _crew_assignment_room,
    _drone_progress,
    _crew_is_working,
    _doorway_crew_position,
    _door_open_amount,
    _mining_bay_progress,
    _mining_bay_tier,
    _movement_direction,
    _manual_crew_task,
    _local_doorway_position,
    _route_via_doorway,
    _shared_alpha_bounds,
    _should_cut_shared_wall,
    _seeded_room_layout,
    _seeded_walk_route,
    _shortest_room_route,
    _task_route_phase,
)


class RecordingScene:
    def __init__(self):
        self.snapshot = None

    def render(self, snapshot):
        self.snapshot = snapshot
        return Image.new("RGB", (4, 3), "black")


class SpaceshipTests(unittest.TestCase):
    def test_active_time_persists_but_offline_gap_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.sqlite"
            start = datetime(2026, 1, 1, tzinfo=timezone.utc)
            store = SpaceshipStateStore(path)
            engine = SpaceshipEngine(RecordingScene(), store, {"save_interval_seconds": 10, "max_tick_seconds": 30})
            engine.consume(PixelOpsEvent.tick(start))
            engine.consume(PixelOpsEvent.tick(start + timedelta(seconds=10)))
            engine.close()

            resumed = SpaceshipEngine(RecordingScene(), SpaceshipStateStore(path), {"save_interval_seconds": 10})
            resumed.consume(PixelOpsEvent.tick(start + timedelta(days=90)))
            resumed.close()

            profile = SpaceshipStateStore(path).profile()
            self.assertEqual(profile.total_active_seconds, 10)
            self.assertGreater(profile.distance_travelled, 0)

    def test_pull_request_becomes_stable_asteroid_and_merge_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SpaceshipStateStore(Path(tmp) / "state.sqlite")
            scene = RecordingScene()
            engine = SpaceshipEngine(scene, store)
            now = datetime(2026, 1, 1, tzinfo=timezone.utc)
            pr = PullRequestSummary(repo="pixel-ops", number=42, title="Engine", author="ana", review_state="review")
            engine.consume(PixelOpsEvent.observation("github.pull_requests_updated", "github", [pr], now))
            merge = WorkEvent(
                category=EventCategory.MERGE, title="pixel-ops #42 merged", source="github",
                repo="pixel-ops", external_id="pixel-ops#42:merged", occurred_at=now,
            )
            engine.consume(merge)
            engine.consume(merge)
            engine.consume(PixelOpsEvent.tick(now))
            engine.render()

            asteroid = store.asteroids()[0]
            self.assertEqual(asteroid.pr_key, "pixel-ops#42")
            self.assertEqual(asteroid.material_type, material_for_pr("pixel-ops#42"))
            self.assertEqual(asteroid.processing_state, "refined")
            self.assertEqual(store.resources()["raw_ore"], 1)
            self.assertEqual(store.resources()["refined_alloy"], 1)
            self.assertEqual(store.receipt_count(), 1)
            self.assertEqual(scene.snapshot.asteroids[0].processing_state, "refined")

    def test_large_confirmed_session_advances_long_term_sector(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SpaceshipStateStore(Path(tmp) / "state.sqlite")
            now = datetime(2026, 4, 1, tzinfo=timezone.utc)

            store.advance_time(90 * 24 * 60 * 60, 0.02, 1 / 60, now)

            profile = store.profile()
            self.assertGreater(profile.ship_level, 100)
            self.assertGreater(profile.current_sector, 50)

    def test_work_event_can_discover_asteroid_before_snapshot_arrives(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SpaceshipStateStore(Path(tmp) / "state.sqlite")
            engine = SpaceshipEngine(RecordingScene(), store)
            now = datetime(2026, 1, 1, tzinfo=timezone.utc)

            engine.consume(WorkEvent(
                category=EventCategory.REVIEW_REQUESTED,
                title="pixel-ops #7 needs review",
                source="github",
                repo="pixel-ops",
                external_id="pixel-ops#7:review-requested",
                occurred_at=now,
            ))

            asteroid = store.asteroids()[0]
            self.assertEqual(asteroid.pr_key, "pixel-ops#7")
            self.assertEqual(asteroid.processing_state, "sampling")
            self.assertEqual(store.resources()["raw_ore"], 1)
            self.assertEqual(store.resources()["mineral_sample"], 1)

    def test_generated_layout_seed_persists_and_explicit_seed_is_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.sqlite"
            generated = SpaceshipStateStore(path).profile().layout_seed
            self.assertEqual(SpaceshipStateStore(path).profile().layout_seed, generated)

            named = SpaceshipStateStore(path, layout_seed="minha-wayfarer").profile().layout_seed
            self.assertNotEqual(named, generated)
            self.assertEqual(
                SpaceshipStateStore(path, layout_seed="minha-wayfarer").profile().layout_seed,
                named,
            )

    def test_seeded_walk_route_only_crosses_adjacent_rooms(self):
        rooms = _seeded_room_layout(4242)
        route = _seeded_walk_route(rooms)

        self.assertTrue(set(rooms).issubset(route))
        for start, end in zip(route, route[1:] + route[:1]):
            self.assertLessEqual(abs(start[0] - end[0]) + abs(start[1] - end[1]), 1)

    def test_pr_state_assigns_crew_to_operational_room(self):
        def asteroid(state: str) -> AsteroidRecord:
            return AsteroidRecord(
                "repo#1", "repo", 1, "iron", state,
                "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00",
            )

        self.assertEqual(_crew_assignment_room(()), "BRIDGE")
        self.assertEqual(_crew_assignment_room((asteroid("sampling"),)), "LAB")
        self.assertEqual(_crew_assignment_room((asteroid("certified"),)), "CARGO")
        self.assertEqual(_crew_assignment_room((asteroid("unstable"),)), "ENGINEERING")

    def test_task_route_uses_only_connected_rooms_and_pauses_to_work(self):
        rooms = _seeded_room_layout(4242)
        start = next(cell for cell, room in rooms.items() if room == "BRIDGE")
        target = next(cell for cell, room in rooms.items() if room == "LAB")
        route = _shortest_room_route(rooms, start, target)

        self.assertEqual(route[0], start)
        self.assertEqual(route[-1], target)
        for left, right in zip(route, route[1:]):
            self.assertEqual(abs(left[0] - right[0]) + abs(left[1] - right[1]), 1)

        simple_route = [(0, 0), (1, 0)]
        epoch = datetime.fromtimestamp(0, timezone.utc)
        self.assertEqual(_task_route_phase(simple_route, epoch)[:2], ((0, 0), (1, 0)))
        self.assertEqual(_task_route_phase(simple_route, epoch + timedelta(seconds=4)), ((1, 0), (1, 0), 0.0, True))
        self.assertEqual(_task_route_phase(simple_route, epoch + timedelta(seconds=11))[:2], ((1, 0), (0, 0)))

    def test_grid_movement_maps_to_isometric_character_direction(self):
        self.assertEqual(_movement_direction((0, 0), (1, 0)), "south-east")
        self.assertEqual(_movement_direction((0, 0), (0, 1)), "south-west")
        self.assertEqual(_movement_direction((1, 0), (0, 0)), "north-west")
        self.assertEqual(_movement_direction((0, 1), (0, 0)), "north-east")

    def test_room_movement_passes_through_shared_doorway(self):
        start_room = (100, 80)
        end_room = (158, 109)
        doorway = _doorway_crew_position(start_room, end_room)
        start = (148, 136)
        end = (206, 165)

        self.assertEqual(_route_via_doorway(start, doorway, end, 0.0), start)
        self.assertEqual(_route_via_doorway(start, doorway, end, 0.5), doorway)
        self.assertEqual(_route_via_doorway(start, doorway, end, 1.0), end)

    def test_room_doorway_openings_match_isometric_neighbor_edges(self):
        self.assertEqual(_local_doorway_position((1, 0)), (84, 92))
        self.assertEqual(_local_doorway_position((0, 1)), (44, 92))
        self.assertEqual(_local_doorway_position((-1, 0)), (44, 72))
        self.assertEqual(_local_doorway_position((0, -1)), (84, 72))

    def test_only_foreground_room_cuts_each_shared_wall(self):
        rooms = {(0, 0): "BRIDGE", (1, 0): "LAB"}

        self.assertTrue(_should_cut_shared_wall((1, 0), (0, 0), rooms))
        self.assertFalse(_should_cut_shared_wall((0, 0), (1, 0), rooms))

    def test_door_opens_before_crossing_and_closes_afterward(self):
        self.assertEqual(_door_open_amount(0.0), 0.0)
        self.assertEqual(_door_open_amount(0.2), 1.0)
        self.assertEqual(_door_open_amount(0.5), 1.0)
        self.assertEqual(_door_open_amount(0.8), 1.0)
        self.assertAlmostEqual(_door_open_amount(0.9), 0.5)
        self.assertEqual(_door_open_amount(1.0), 0.0)

    def test_animation_frames_share_one_crop_to_prevent_size_pulsing(self):
        wide = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        narrow = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        wide.paste((255, 255, 255, 255), (2, 3, 14, 15))
        narrow.paste((255, 255, 255, 255), (5, 5, 11, 13))

        self.assertEqual(_shared_alpha_bounds([wide, narrow]), (2, 3, 14, 15))

    def test_crew_work_cycle_alternates_action_and_idle(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        phase_start = start - timedelta(seconds=int(start.timestamp()) % 12)

        self.assertTrue(_crew_is_working(phase_start))
        self.assertTrue(_crew_is_working(phase_start + timedelta(seconds=7)))
        self.assertFalse(_crew_is_working(phase_start + timedelta(seconds=8)))

    def test_manual_crew_task_selects_pixellab_character_state(self):
        config = {"manual_tasks": {"operations_officer": "working_on_computer"}}

        self.assertEqual(_manual_crew_task(config, "operations_officer"), "working_on_computer")
        self.assertIsNone(_manual_crew_task(config, "maintenance_engineer"))

    def test_mining_drone_prioritizes_sampling_over_detected_asteroids(self):
        asteroids = (
            AsteroidRecord("repo#1", "repo", 1, "iron", "detected", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00"),
            AsteroidRecord("repo#2", "repo", 2, "cobalt", "sampling", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:02+00:00"),
        )

        self.assertEqual(_active_mining_asteroid(asteroids).pr_key, "repo#2")

    def test_drone_approaches_for_review_and_returns_after_approval(self):
        started = datetime(2026, 1, 1, tzinfo=timezone.utc)
        timestamp = started.isoformat()

        self.assertEqual(_drone_progress("sampling", timestamp, started), 0.0)
        self.assertEqual(_drone_progress("sampling", timestamp, started + timedelta(seconds=5)), 1.0)
        self.assertEqual(_drone_progress("certified", timestamp, started), 1.0)
        self.assertEqual(_drone_progress("certified", timestamp, started + timedelta(seconds=5)), 0.0)
        self.assertIsNone(_drone_progress("certified", timestamp, started + timedelta(seconds=9)))

    def test_refined_prs_unlock_persistent_mining_bay_tiers(self):
        self.assertEqual(_mining_bay_tier({"refined_alloy": 0}), 1)
        self.assertEqual(_mining_bay_tier({"refined_alloy": 59}), 1)
        self.assertEqual(_mining_bay_tier({"refined_alloy": 60}), 2)
        self.assertEqual(_mining_bay_tier({"refined_alloy": 180}), 4)
        self.assertEqual(_mining_bay_progress({"refined_alloy": 79}), (2, 19, 60))


if __name__ == "__main__":
    unittest.main()
