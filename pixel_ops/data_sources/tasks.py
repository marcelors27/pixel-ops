from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
    parent_id: str = ""
    assignee: str = ""
    column: str = ""
    order: int = 0


@dataclass(frozen=True)
class TaskSnapshot:
    tasks: tuple[TaskItem, ...]
    observed_at: datetime
    provider: str = ""


class TaskSource(Protocol):
    def current(self, now: datetime | None = None) -> TaskSnapshot | None:
        ...


class MergedTaskSource:
    def __init__(self, sources: list[TaskSource] | tuple[TaskSource, ...] | None = None, max_tasks: int = 24):
        self.sources = list(sources or [])
        self.max_tasks = max(1, int(max_tasks))

    def add(self, source: TaskSource) -> None:
        self.sources.append(source)

    def current(self, now: datetime | None = None) -> TaskSnapshot | None:
        base_now = now or datetime.now().astimezone()
        snapshots = [snapshot for source in self.sources if (snapshot := source.current(base_now)) is not None]
        if not snapshots:
            return None
        tasks: list[TaskItem] = []
        for snapshot in snapshots:
            tasks.extend(snapshot.tasks)
        ordered = sorted(tasks, key=_task_sort_key)[: self.max_tasks]
        providers = [snapshot.provider for snapshot in snapshots if snapshot.provider]
        provider = "+".join(dict.fromkeys(providers))
        observed_at = max((snapshot.observed_at for snapshot in snapshots), default=base_now)
        return TaskSnapshot(tasks=tuple(ordered), observed_at=observed_at, provider=provider)


def _task_sort_key(task: TaskItem):
    return (task.due_at or datetime.max.replace(tzinfo=timezone.utc), task.order, task.title.lower(), task.id)
