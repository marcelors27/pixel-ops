from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from PIL import Image

from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.data_sources.timezones import build_people_times
from pixel_ops.events.github_events import GitHubEventSource


class PixelOpsScene(Protocol):
    def render(self, people_times, next_event, now: datetime, pull_requests) -> Image.Image:
        ...


class PixelOpsApp:
    """Hardware-agnostic frame producer for a Pixel OPs interface plugin."""

    def __init__(
        self,
        scene: PixelOpsScene,
        people_config: list[dict],
        next_event: Callable[[datetime], CalendarEvent | None],
        github_source: GitHubEventSource,
    ):
        self.scene = scene
        self.people_config = people_config
        self.next_event = next_event
        self.github_source = github_source

    def render_frame(self, now: datetime) -> Image.Image:
        return self.scene.render(
            build_people_times(self.people_config, now),
            self.next_event(now),
            now,
            self.github_source.open_pull_requests(now),
        )
