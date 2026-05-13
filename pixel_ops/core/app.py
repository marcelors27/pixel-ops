from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from PIL import Image

from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.data_sources.timezones import build_people_times
from pixel_ops.data_sources.weather import OpenMeteoWeatherSource
from pixel_ops.events.github_events import GitHubEventSource


class PixelOpsScene(Protocol):
    def render(self, people_times, next_event, now: datetime, pull_requests, weather) -> Image.Image:
        ...


class PixelOpsApp:
    """Hardware-agnostic frame producer for a Pixel OPs interface plugin."""

    def __init__(
        self,
        scene: PixelOpsScene,
        people_config: list[dict],
        next_event: Callable[[datetime], CalendarEvent | None],
        github_source: GitHubEventSource,
        weather_source: OpenMeteoWeatherSource | None = None,
    ):
        self.scene = scene
        self.people_config = people_config
        self.next_event = next_event
        self.github_source = github_source
        self.weather_source = weather_source

    def render_frame(self, now: datetime) -> Image.Image:
        return self.scene.render(
            build_people_times(self.people_config, now),
            self.next_event(now),
            now,
            self.github_source.open_pull_requests(now),
            self.weather_source.current(now) if self.weather_source else None,
        )
