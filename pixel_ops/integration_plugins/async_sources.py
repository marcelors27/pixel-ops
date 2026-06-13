from __future__ import annotations

import sys
import time
from collections.abc import Callable
from datetime import datetime
from threading import Lock, Thread
from typing import Any


class AsyncCurrentSource:
    """Returns the latest snapshot while refreshing a source off the render loop."""

    def __init__(self, source: Any, method_name: str = "current", interval_seconds: float | None = None):
        self._source = source
        self._method_name = method_name
        self._interval_seconds = _source_interval(source, interval_seconds)
        self._lock = Lock()
        self._running = False
        self._last_attempt_at = 0.0
        self._snapshot = None

    def current(self, now: datetime | None = None):
        self._schedule(now)
        with self._lock:
            return self._snapshot

    def _schedule(self, now: datetime | None) -> None:
        monotonic_now = time.monotonic()
        with self._lock:
            if self._running:
                return
            if self._last_attempt_at and monotonic_now - self._last_attempt_at < self._interval_seconds:
                return
            self._running = True
            self._last_attempt_at = monotonic_now
        Thread(target=self._refresh, args=(now,), daemon=True).start()

    def _refresh(self, now: datetime | None) -> None:
        try:
            method = getattr(self._source, self._method_name)
            snapshot = method(now)
            with self._lock:
                self._snapshot = snapshot
        except Exception as error:  # pragma: no cover - defensive integration boundary
            print(f"[pixel-ops integration] {type(self._source).__name__}.{self._method_name} failed: {error}", file=sys.stderr)
        finally:
            with self._lock:
                self._running = False

    def __getattr__(self, name: str):
        return getattr(self._source, name)


class AsyncPullRequestSource:
    def __init__(self, source: Any, interval_seconds: float | None = None):
        self._source = source
        self._interval_seconds = _source_interval(source, interval_seconds)
        self._lock = Lock()
        self._running = False
        self._last_attempt_at = 0.0
        self._pull_requests: list = []

    def open_pull_requests(self, now: datetime | None = None) -> list:
        self._schedule(now)
        with self._lock:
            return list(self._pull_requests)

    def poll(self, now: datetime):
        poll = getattr(self._source, "poll", None)
        return poll(now) if callable(poll) else []

    def _schedule(self, now: datetime | None) -> None:
        monotonic_now = time.monotonic()
        with self._lock:
            if self._running:
                return
            if self._last_attempt_at and monotonic_now - self._last_attempt_at < self._interval_seconds:
                return
            self._running = True
            self._last_attempt_at = monotonic_now
        Thread(target=self._refresh, args=(now,), daemon=True).start()

    def _refresh(self, now: datetime | None) -> None:
        try:
            pull_requests = self._source.open_pull_requests(now)
            with self._lock:
                self._pull_requests = list(pull_requests or [])
        except Exception as error:  # pragma: no cover - defensive integration boundary
            print(f"[pixel-ops integration] {type(self._source).__name__}.open_pull_requests failed: {error}", file=sys.stderr)
        finally:
            with self._lock:
                self._running = False

    def __getattr__(self, name: str):
        return getattr(self._source, name)


class AsyncEventSource:
    """Polls event sources in the background and drains completed events per frame."""

    def __init__(self, source: Any, interval_seconds: float | None = None):
        self._source = source
        self._interval_seconds = _source_interval(source, interval_seconds)
        self._lock = Lock()
        self._running = False
        self._last_attempt_at = 0.0
        self._pending_events: list = []

    def poll(self, now: datetime) -> list:
        with self._lock:
            events = self._pending_events
            self._pending_events = []
        self._schedule(now)
        return events

    def _schedule(self, now: datetime) -> None:
        monotonic_now = time.monotonic()
        with self._lock:
            if self._running:
                return
            if self._last_attempt_at and monotonic_now - self._last_attempt_at < self._interval_seconds:
                return
            self._running = True
            self._last_attempt_at = monotonic_now
        Thread(target=self._refresh, args=(now,), daemon=True).start()

    def _refresh(self, now: datetime) -> None:
        try:
            events = self._source.poll(now)
            if events:
                with self._lock:
                    self._pending_events.extend(events)
        except Exception as error:  # pragma: no cover - defensive integration boundary
            print(f"[pixel-ops integration] {type(self._source).__name__}.poll failed: {error}", file=sys.stderr)
        finally:
            with self._lock:
                self._running = False

    def __getattr__(self, name: str):
        return getattr(self._source, name)


def run_background(action: Callable[[], None], label: str) -> Callable[[], None]:
    def start() -> None:
        Thread(target=_run_safely, args=(action, label), daemon=True).start()

    return start


def _run_safely(action: Callable[[], None], label: str) -> None:
    try:
        action()
    except Exception as error:  # pragma: no cover - defensive integration boundary
        print(f"[pixel-ops integration] {label} failed: {error}", file=sys.stderr)


def _source_interval(source: Any, fallback: float | None) -> float:
    if fallback is not None:
        return max(0.1, float(fallback))
    try:
        return max(0.1, float(getattr(source, "poll_seconds")))
    except (AttributeError, TypeError, ValueError):
        return 1.0
