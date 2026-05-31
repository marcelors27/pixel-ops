from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class TaskItem:
    provider: str
    id: str
    title: str
    status: str
    due_at: datetime | None
    url: str = ""
    group: str = ""


@dataclass(frozen=True)
class TaskSnapshot:
    tasks: tuple[TaskItem, ...]
    observed_at: datetime
    provider: str = ""


class TaskSource(Protocol):
    def current(self, now: datetime | None = None) -> TaskSnapshot | None:
        ...
