from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from PIL import Image

from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.data_sources.companions import CompanionSource
from pixel_ops.data_sources.gamification import GamificationSource
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
        companion_snapshot=None,
        today_events=None,
        gamification=None,
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
        today_events: Callable[[datetime], list[CalendarEvent]] | None = None,
        weather_source: WeatherSource | None = None,
        ai_usage_source: AIUsageSource | None = None,
        pc_stats_source: PCStatsSource | None = None,
        task_source: TaskSource | None = None,
        media_source: MediaSource | None = None,
        companion_source: CompanionSource | None = None,
        gamification_source: GamificationSource | None = None,
    ):
        self.scene = scene
        self.people_config = people_config
        self.next_event = next_event
        self.today_events = today_events
        self.pull_request_source = pull_request_source
        self.weather_source = weather_source
        self.ai_usage_source = ai_usage_source
        self.pc_stats_source = pc_stats_source
        self.task_source = task_source
        self.media_source = media_source
        self.companion_source = companion_source
        self.gamification_source = gamification_source

    def render_frame(self, now: datetime) -> Image.Image:
        task_snapshot = self.task_source.current(now) if self.task_source else None
        companion_snapshot = self.companion_source.current(now) if self.companion_source else None
        today_events = self.today_events(now) if self.today_events else []
        kwargs = {
            "pc_stats": self.pc_stats_source.current(now) if self.pc_stats_source else None,
            "task_snapshot": task_snapshot,
            "media": self.media_source.current(now) if self.media_source else None,
            "today_events": today_events,
        }
        if companion_snapshot:
            kwargs["companion_snapshot"] = companion_snapshot
        if self.gamification_source:
            kwargs["gamification"] = self.gamification_source.current(
                now,
                today_events=today_events,
                task_snapshot=task_snapshot,
                companion_snapshot=companion_snapshot,
            )
        return self.scene.render(
            build_people_times(self.people_config, now),
            self.next_event(now),
            now,
            self.pull_request_source.open_pull_requests(now),
            self.weather_source.current(now) if self.weather_source else None,
            self.ai_usage_source.current(now) if self.ai_usage_source else None,
            **kwargs,
        )
