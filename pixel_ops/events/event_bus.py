from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass
class EventBus(Generic[T]):
    """Tiny in-process bus for sequential ambient events.

    The display loop is single-process today, so a bounded deque is enough. It
    gives integrations a neutral publish point without forcing the renderer to
    know about Slack, Discord, or calendar transport details.
    """

    maxlen: int = 128
    _queue: deque[T] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._queue = deque(maxlen=self.maxlen)

    def publish(self, event: T) -> None:
        self._queue.append(event)

    append = publish

    def drain(self, limit: int | None = None) -> list[T]:
        events: list[T] = []
        while self._queue and (limit is None or len(events) < limit):
            events.append(self._queue.popleft())
        return events

    def __len__(self) -> int:
        return len(self._queue)


@dataclass(frozen=True)
class BusEnvelope(Generic[T]):
    event: T
    published_at: datetime
