from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from PIL import Image

from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.data_sources.timezones import build_people_times


class PullRequestSource(Protocol):
    def open_pull_requests(self, now: datetime | None = None) -> list:
        ...


class WeatherSource(Protocol):
    def current(self, now: datetime):
        ...


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
        pull_request_source: PullRequestSource,
        weather_source: WeatherSource | None = None,
    ):
        self.scene = scene
        self.people_config = people_config
        self.next_event = next_event
        self.pull_request_source = pull_request_source
        self.weather_source = weather_source

    def render_frame(self, now: datetime) -> Image.Image:
        return self.scene.render(
            build_people_times(self.people_config, now),
            self.next_event(now),
            now,
            self.pull_request_source.open_pull_requests(now),
            self.weather_source.current(now) if self.weather_source else None,
        )
