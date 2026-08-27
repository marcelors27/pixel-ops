from __future__ import annotations

from datetime import datetime

from PIL import Image

from pixel_ops.data_sources.companions import CompanionSnapshot, calendar_companion_snapshot, merge_companion_snapshots
from pixel_ops.data_sources.gamification import GamificationSource
from pixel_ops.data_sources.timezones import build_people_times
from pixel_ops.events.base import WorkEvent
from pixel_ops.events.platform import PixelOpsEvent
from pixel_ops.plugins.pokemon.scenes.overworld_scene import OverworldScene


class PokemonEngine:
    """Pokemon-owned projection of the neutral Pixel Ops event stream."""

    name = "pokemon"

    def __init__(self, scene: OverworldScene, people_config: list[dict], gamification: GamificationSource | None = None):
        self.scene = scene
        self.people_config = people_config
        self.gamification_source = gamification
        self.now: datetime | None = None
        self.values: dict[str, object] = {}

    def consume(self, event: PixelOpsEvent | WorkEvent) -> None:
        if isinstance(event, WorkEvent):
            self.scene.encounter_system.enqueue(event)
            return
        if event.type == "runtime.tick":
            self.now = event.occurred_at
            return
        if event.type == "people.updated":
            value = event.payload.get("value")
            if isinstance(value, list):
                self.people_config = value
            return
        value = event.payload.get("value")
        if event.type == "social.companions_updated" and isinstance(value, CompanionSnapshot):
            current = self.values.get(event.type)
            if isinstance(current, CompanionSnapshot) and current is not value:
                value = merge_companion_snapshots(current, value)
        self.values[event.type] = value

    def render(self) -> Image.Image:
        if self.now is None:
            raise RuntimeError("PokemonEngine requires runtime.tick before render")
        today_events = self._list("calendar.today_updated")
        task_snapshot = self.values.get("tasks.snapshot_updated")
        project_snapshot = self.values.get("projects.snapshot_updated")
        companion_snapshot = self.values.get("social.companions_updated")
        meeting_companions = calendar_companion_snapshot(today_events, self.now)
        if isinstance(companion_snapshot, CompanionSnapshot):
            companion_snapshot = merge_companion_snapshots(companion_snapshot, meeting_companions)
        elif meeting_companions is not None:
            companion_snapshot = meeting_companions
        gamification = None
        if self.gamification_source:
            gamification = self.gamification_source.current(
                self.now,
                today_events=today_events,
                task_snapshot=task_snapshot,
                companion_snapshot=companion_snapshot,
            )
        return self.scene.render(
            build_people_times(self.people_config, self.now),
            self.values.get("calendar.next_updated"),
            self.now,
            self._list("github.pull_requests_updated"),
            self.values.get("weather.conditions_updated"),
            self.values.get("ai.usage_updated"),
            pc_stats=self.values.get("system.metrics_updated"),
            task_snapshot=task_snapshot,
            project_snapshot=project_snapshot,
            media=self.values.get("media.playback_updated"),
            companion_snapshot=companion_snapshot,
            today_events=today_events,
            gamification=gamification,
            crosshero=self.values.get("fitness.crosshero_day_updated"),
        )

    def set_presentation(self, layout: dict, layout_theme: str) -> None:
        self.scene.set_presentation(layout, layout_theme)

    def close(self) -> None:
        return None

    def _list(self, event_type: str) -> list:
        value = self.values.get(event_type)
        return value if isinstance(value, list) else []
