from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from pixel_ops.data_sources.calendar import CalendarEvent
from pixel_ops.data_sources.companions import CompanionSnapshot
from pixel_ops.data_sources.tasks import TaskItem, TaskSnapshot


@dataclass(frozen=True)
class GamificationSnapshot:
    hp: float
    max_hp: float
    meetings_finished: int = 0
    tasks_delivered: int = 0
    companion_count: int = 0
    recovery_per_hour: float = 0.0
    status: str = "steady"

    @property
    def hp_percent(self) -> float:
        if self.max_hp <= 0:
            return 0.0
        return max(0.0, min(100.0, self.hp / self.max_hp * 100.0))


class GamificationSource:
    def __init__(
        self,
        *,
        max_hp: float = 100.0,
        meeting_cost: float = 8.0,
        task_delivered_cost: float = 5.0,
        base_recovery_per_hour: float = 0.0,
        companion_recovery_per_hour: float = 4.0,
        max_companion_bonus: int = 5,
    ):
        self.max_hp = max(1.0, float(max_hp))
        self.meeting_cost = max(0.0, float(meeting_cost))
        self.task_delivered_cost = max(0.0, float(task_delivered_cost))
        self.base_recovery_per_hour = max(0.0, float(base_recovery_per_hour))
        self.companion_recovery_per_hour = max(0.0, float(companion_recovery_per_hour))
        self.max_companion_bonus = max(0, int(max_companion_bonus))
        self._hp = self.max_hp
        self._day: date | None = None
        self._last_seen_at: datetime | None = None
        self._seen_meetings: set[str] = set()
        self._seen_tasks: set[str] = set()
        self._meetings_finished = 0
        self._tasks_delivered = 0

    def current(
        self,
        now: datetime,
        *,
        today_events: list[CalendarEvent] | None = None,
        task_snapshot: TaskSnapshot | None = None,
        companion_snapshot: CompanionSnapshot | None = None,
    ) -> GamificationSnapshot:
        events = today_events or []
        self._reset_if_new_day(now)
        delivered_tasks = [task for task in (task_snapshot.tasks if task_snapshot else ()) if _task_delivered(task)]
        companion_count = len(companion_snapshot.members) if companion_snapshot else 0
        recovery_per_hour = self.base_recovery_per_hour + min(companion_count, self.max_companion_bonus) * self.companion_recovery_per_hour
        self._recover(now, recovery_per_hour if companion_count else self.base_recovery_per_hour)
        self._consume_finished_meetings(events, now)
        self._consume_delivered_tasks(delivered_tasks)
        return GamificationSnapshot(
            hp=self._hp,
            max_hp=self.max_hp,
            meetings_finished=self._meetings_finished,
            tasks_delivered=self._tasks_delivered,
            companion_count=companion_count,
            recovery_per_hour=recovery_per_hour if companion_count else 0.0,
            status=_hp_status(self._hp / self.max_hp),
        )

    def _reset_if_new_day(self, now: datetime) -> None:
        if self._day == now.date():
            return
        self._day = now.date()
        self._hp = self.max_hp
        self._last_seen_at = now
        self._seen_meetings.clear()
        self._seen_tasks.clear()
        self._meetings_finished = 0
        self._tasks_delivered = 0

    def _recover(self, now: datetime, recovery_per_hour: float) -> None:
        if self._last_seen_at is None:
            self._last_seen_at = now
            return
        elapsed_hours = max(0.0, (now - self._last_seen_at).total_seconds() / 3600.0)
        self._last_seen_at = now
        if elapsed_hours > 0 and recovery_per_hour > 0:
            self._hp = min(self.max_hp, self._hp + elapsed_hours * recovery_per_hour)

    def _consume_finished_meetings(self, events: list[CalendarEvent], now: datetime) -> None:
        for event in events:
            key = _meeting_key(event)
            if key in self._seen_meetings or not _event_finished(event, now):
                continue
            self._seen_meetings.add(key)
            self._meetings_finished += 1
            self._hp = max(0.0, self._hp - self.meeting_cost)

    def _consume_delivered_tasks(self, tasks: list[TaskItem]) -> None:
        for task in tasks:
            key = f"{task.provider}:{task.id or task.title}"
            if key in self._seen_tasks:
                continue
            self._seen_tasks.add(key)
            self._tasks_delivered += 1
            self._hp = max(0.0, self._hp - self.task_delivered_cost)


def _event_finished(event: CalendarEvent, now: datetime) -> bool:
    if event.all_day:
        return False
    end_at = event.ends_at or event.starts_at + timedelta(minutes=30)
    return end_at <= now


def _task_delivered(task: TaskItem) -> bool:
    normalized = f"{task.status} {task.column}".lower().replace("_", " ").replace("-", " ")
    delivered_terms = ("done", "closed", "complete", "completed", "delivered", "shipped", "released", "resolved")
    return any(term in normalized for term in delivered_terms)


def _meeting_key(event: CalendarEvent) -> str:
    end_at = event.ends_at or event.starts_at + timedelta(minutes=30)
    return f"{event.title}|{event.starts_at.isoformat()}|{end_at.isoformat()}"


def _hp_status(ratio: float) -> str:
    if ratio <= 0.25:
        return "critical"
    if ratio <= 0.5:
        return "low"
    if ratio >= 0.9:
        return "rested"
    return "steady"
