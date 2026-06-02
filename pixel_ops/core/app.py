from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from PIL import Image

from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.data_sources.tasks import TaskSource
from pixel_ops.data_sources.timezones import build_people_times


class PullRequestSource(Protocol):
    def open_pull_requests(self, now: datetime | None = None) -> list:
        ...


class WeatherSource(Protocol):
    def current(self, now: datetime):
        ...


class AIUsageSource(Protocol):
    def current(self, now: datetime | None = None):
        ...


class PCStatsSource(Protocol):
    def current(self, now: datetime | None = None):
        ...


class MediaSource(Protocol):
    def current(self, now: datetime | None = None):
        ...


class PixelOpsScene(Protocol):
    def render(
        self,
        people_times,
        next_event,
        now: datetime,
        pull_requests,
        weather,
        ai_usage,
        pc_stats=None,
        task_snapshot=None,
        media=None,
    ) -> Image.Image:
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
        ai_usage_source: AIUsageSource | None = None,
        pc_stats_source: PCStatsSource | None = None,
        task_source: TaskSource | None = None,
        media_source: MediaSource | None = None,
    ):
        self.scene = scene
        self.people_config = people_config
        self.next_event = next_event
        self.pull_request_source = pull_request_source
        self.weather_source = weather_source
        self.ai_usage_source = ai_usage_source
        self.pc_stats_source = pc_stats_source
        self.task_source = task_source
        self.media_source = media_source

    def render_frame(self, now: datetime) -> Image.Image:
        return self.scene.render(
            build_people_times(self.people_config, now),
            self.next_event(now),
            now,
            self.pull_request_source.open_pull_requests(now),
            self.weather_source.current(now) if self.weather_source else None,
            self.ai_usage_source.current(now) if self.ai_usage_source else None,
            self.pc_stats_source.current(now) if self.pc_stats_source else None,
            self.task_source.current(now) if self.task_source else None,
            self.media_source.current(now) if self.media_source else None,
        )
