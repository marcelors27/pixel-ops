from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread

from pixel_ops.data_sources.calendar import download_ics, next_ics_event
from pixel_ops.events.base import WorkEvent
from pixel_ops.events.meeting_events import work_event_for_meeting


class CalendarEventSource:
    """Polls an ICS calendar and emits meeting encounters."""

    def __init__(
        self,
        enabled: bool = False,
        path: str | Path | None = None,
        url: str = "",
        cache_path: str | Path | None = None,
        poll_seconds: int = 300,
        lookahead_minutes: int = 45,
    ):
        self.enabled = enabled
        self.path = Path(path) if path else None
        self.url = url
        self.cache_path = Path(cache_path) if cache_path else None
        self.poll_seconds = poll_seconds
        self.lookahead = timedelta(minutes=lookahead_minutes)
        self._last_poll_at: datetime | None = None
        self._download_running = False

    def poll(self, now: datetime) -> list[WorkEvent]:
        if not self.enabled:
            return []
        if self._last_poll_at and (now - self._last_poll_at).total_seconds() < self.poll_seconds:
            return []
        self._last_poll_at = now

        path = self._calendar_path()
        if not path:
            return []

        event = next_ics_event(path, now)
        if not event or event.starts_at - now > self.lookahead:
            return []

        return [work_event_for_meeting(event.title, event.starts_at, now)]

    def _calendar_path(self) -> Path | None:
        if self.url and self.cache_path:
            self._refresh_async()
            return self.cache_path if self.cache_path.exists() else None
        if self.path and self.path.exists():
            return self.path
        if self.cache_path and self.cache_path.exists():
            return self.cache_path
        return None

    def warm_cache(self) -> None:
        if self.url and self.cache_path:
            download_ics(self.url, self.cache_path)

    def _refresh_async(self) -> None:
        if self._download_running:
            return
        self._download_running = True

        def worker() -> None:
            try:
                download_ics(self.url, self.cache_path)
            finally:
                self._download_running = False

        Thread(target=worker, daemon=True).start()
