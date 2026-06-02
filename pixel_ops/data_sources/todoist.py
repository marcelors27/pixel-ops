from __future__ import annotations

import os
from datetime import datetime, time, timezone
from typing import Any

import requests

from pixel_ops.data_sources.tasks import TaskItem, TaskSnapshot


TODOIST_API_BASE_URL = "https://api.todoist.com/rest/v2"


class TodoistTaskSource:
    def __init__(
        self,
        enabled: bool = True,
        token_env: str = "PIXEL_OPS_TODOIST_TOKEN",
        poll_seconds: int = 120,
        max_tasks: int = 12,
        due_within_days: int = 14,
        include_overdue: bool = True,
        include_undated: bool = True,
        project_ids: list[str] | tuple[str, ...] | str | None = None,
        section_ids: list[str] | tuple[str, ...] | str | None = None,
        filter: str = "",
        timeout_seconds: int = 10,
        api_base_url: str = TODOIST_API_BASE_URL,
    ):
        self.enabled = enabled
        self.token_env = token_env
        self.poll_seconds = max(1, int(poll_seconds))
        self.max_tasks = max(1, int(max_tasks))
        self.due_within_days = max(1, int(due_within_days))
        self.include_overdue = include_overdue
        self.include_undated = include_undated
        self.project_ids = _ids_from_config(project_ids)
        self.section_ids = _ids_from_config(section_ids)
        self.filter = str(filter or "").strip()
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.api_base_url = api_base_url.rstrip("/")
        self._last_poll_at: datetime | None = None
        self._snapshot: TaskSnapshot | None = None

    def current(self, now: datetime | None = None) -> TaskSnapshot | None:
        if not self.enabled:
            return None
        base_now = now or datetime.now().astimezone()
        if self._last_poll_at and (base_now - self._last_poll_at).total_seconds() < self.poll_seconds:
            return self._snapshot
        self._last_poll_at = base_now
        try:
            self._snapshot = TaskSnapshot(tasks=tuple(self._fetch_tasks(base_now)), observed_at=base_now, provider="todoist")
        except (requests.RequestException, ValueError, KeyError, TypeError):
            if self._snapshot is None:
                self._snapshot = TaskSnapshot(tasks=(), observed_at=base_now, provider="todoist")
        return self._snapshot

    def _fetch_tasks(self, now: datetime) -> list[TaskItem]:
        token = os.environ.get(self.token_env, "").strip()
        if not token:
            raise ValueError(f"{self.token_env} is required for Todoist tasks")
        projects = self._project_names(token)
        sections = self._section_names(token)
        payloads: list[dict[str, Any]] = []
        for params in self._task_queries():
            payload = self._get_json(token, "/tasks", params=params)
            if isinstance(payload, list):
                payloads.extend(item for item in payload if isinstance(item, dict))
        seen: set[str] = set()
        tasks: list[TaskItem] = []
        due_until = now.timestamp() + self.due_within_days * 86400
        for item in payloads:
            task = _task_from_payload(item, projects, sections)
            if task.id in seen or not self._include_task(task, now, due_until):
                continue
            seen.add(task.id)
            tasks.append(task)
        return sorted(tasks, key=_task_sort_key)[: self.max_tasks]

    def _task_queries(self) -> list[list[tuple[str, str]]]:
        if self.filter:
            return [[("filter", self.filter)]]
        queries: list[list[tuple[str, str]]] = []
        queries.extend([[("project_id", project_id)] for project_id in self.project_ids])
        queries.extend([[("section_id", section_id)] for section_id in self.section_ids])
        return queries or [[]]

    def _include_task(self, task: TaskItem, now: datetime, due_until: float) -> bool:
        if task.due_at is None:
            return self.include_undated
        due_timestamp = task.due_at.timestamp()
        if due_timestamp >= due_until:
            return False
        if not self.include_overdue and due_timestamp <= now.timestamp():
            return False
        return True

    def _project_names(self, token: str) -> dict[str, str]:
        payload = self._get_json(token, "/projects")
        if not isinstance(payload, list):
            return {}
        return {str(item.get("id")): str(item.get("name") or "") for item in payload if isinstance(item, dict)}

    def _section_names(self, token: str) -> dict[str, str]:
        payload = self._get_json(token, "/sections")
        if not isinstance(payload, list):
            return {}
        return {str(item.get("id")): str(item.get("name") or "") for item in payload if isinstance(item, dict)}

    def _get_json(self, token: str, path: str, params: list[tuple[str, str]] | None = None) -> Any:
        response = requests.get(
            f"{self.api_base_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()


def _task_from_payload(item: dict[str, Any], projects: dict[str, str], sections: dict[str, str]) -> TaskItem:
    project_id = str(item.get("project_id") or "")
    section_id = str(item.get("section_id") or "")
    section_name = sections.get(section_id, "")
    status = section_name or "Inbox"
    return TaskItem(
        provider="todoist",
        id=str(item.get("id") or ""),
        title=str(item.get("content") or "Untitled task"),
        status=status,
        due_at=_due_datetime(item.get("due")),
        url=str(item.get("url") or ""),
        group=projects.get(project_id, ""),
        parent_id=str(item.get("parent_id") or ""),
        column=status,
        order=int(item.get("order") or 0),
    )


def _due_datetime(value: object) -> datetime | None:
    if not isinstance(value, dict):
        return None
    raw = str(value.get("datetime") or value.get("date") or "").strip()
    if not raw:
        return None
    try:
        if "T" in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone()
        return datetime.combine(datetime.fromisoformat(raw).date(), time.max, tzinfo=timezone.utc).astimezone()
    except ValueError:
        return None


def _ids_from_config(value: list[str] | tuple[str, ...] | str | None) -> list[str]:
    if isinstance(value, str):
        raw_items = value.split(",")
    elif value is None:
        raw_items = []
    else:
        raw_items = list(value)
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _task_sort_key(task: TaskItem):
    return (task.due_at or datetime.max.replace(tzinfo=timezone.utc), task.order, task.title.lower(), task.id)
