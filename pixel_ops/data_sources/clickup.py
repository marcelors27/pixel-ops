from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests

from pixel_ops.data_sources.tasks import TaskItem, TaskSnapshot


CLICKUP_API_BASE_URL = "https://api.clickup.com/api/v2"


class ClickUpTaskSource:
    def __init__(
        self,
        enabled: bool = True,
        token_env: str = "PIXEL_OPS_CLICKUP_TOKEN",
        team_id: str = "",
        team_ids: list[str] | tuple[str, ...] | str | None = None,
        assignee_id: str = "",
        assignee_ids: list[str] | tuple[str, ...] | str | None = None,
        poll_seconds: int = 120,
        max_tasks: int = 5,
        due_within_days: int = 14,
        include_overdue: bool = True,
        include_undated: bool = True,
        include_subtasks: bool = True,
        include_closed: bool = False,
        timeout_seconds: int = 10,
        api_base_url: str = CLICKUP_API_BASE_URL,
    ):
        self.enabled = enabled
        self.token_env = token_env
        self.team_id = str(team_id or "").strip()
        self.team_ids = _ids_from_config(team_ids, self.team_id)
        self.assignee_id = str(assignee_id or "").strip()
        self.assignee_ids = _ids_from_config(assignee_ids, self.assignee_id)
        self.poll_seconds = max(1, int(poll_seconds))
        self.max_tasks = max(1, int(max_tasks))
        self.due_within_days = max(1, int(due_within_days))
        self.include_overdue = include_overdue
        self.include_undated = include_undated
        self.include_subtasks = include_subtasks
        self.include_closed = include_closed
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.api_base_url = api_base_url.rstrip("/")
        self._last_poll_at: datetime | None = None
        self._snapshot: TaskSnapshot | None = None
        self._resolved_team_ids: list[str] | None = self.team_ids or None
        self._resolved_assignee_ids: list[str] | None = self.assignee_ids or None

    def current(self, now: datetime | None = None) -> TaskSnapshot | None:
        if not self.enabled:
            return None
        base_now = now or datetime.now().astimezone()
        if self._last_poll_at and (base_now - self._last_poll_at).total_seconds() < self.poll_seconds:
            return self._snapshot
        self._last_poll_at = base_now
        try:
            self._snapshot = TaskSnapshot(tasks=tuple(self._fetch_tasks(base_now)), observed_at=base_now, provider="clickup")
        except (requests.RequestException, ValueError, KeyError, TypeError):
            if self._snapshot is None:
                self._snapshot = TaskSnapshot(tasks=(), observed_at=base_now, provider="clickup")
        return self._snapshot

    def _fetch_tasks(self, now: datetime) -> list[TaskItem]:
        token = os.environ.get(self.token_env, "").strip()
        if not token:
            raise ValueError(f"{self.token_env} is required for ClickUp tasks")
        due_until = now.timestamp() + self.due_within_days * 86400
        tasks: list[TaskItem] = []
        for team_id in self._team_ids(token):
            params: list[tuple[str, str]] = [
                ("include_closed", _bool_param(self.include_closed)),
                ("subtasks", _bool_param(self.include_subtasks)),
                ("order_by", "due_date"),
                ("reverse", "false"),
                ("page", "0"),
            ]
            params.extend(("assignees[]", assignee_id) for assignee_id in self._assignee_ids(token))
            if not self.include_undated:
                params.append(("due_date_lt", str(int(due_until * 1000))))
            if not self.include_overdue and not self.include_undated:
                params.append(("due_date_gt", str(int(now.timestamp() * 1000))))
            payload = self._get_json(token, f"/team/{team_id}/task", params=params)
            tasks.extend(_task_from_payload(item) for item in payload.get("tasks", []) if isinstance(item, dict))
        tasks = [task for task in tasks if self._include_task(task, now, due_until)]
        tasks.extend(self._fetch_missing_parent_tasks(token, tasks))
        return _order_parent_tasks_with_subtasks(tasks)[: self.max_tasks]

    def _include_task(self, task: TaskItem, now: datetime, due_until: float) -> bool:
        if task.due_at is None:
            return self.include_undated
        due_timestamp = task.due_at.timestamp()
        if due_timestamp >= due_until:
            return False
        if not self.include_overdue and due_timestamp <= now.timestamp():
            return False
        return True

    def _fetch_missing_parent_tasks(self, token: str, tasks: list[TaskItem]) -> list[TaskItem]:
        if not self.include_subtasks:
            return []
        task_ids = {task.id for task in tasks}
        parent_ids = sorted({task.parent_id for task in tasks if task.parent_id and task.parent_id not in task_ids})
        parents: list[TaskItem] = []
        for parent_id in parent_ids[: self.max_tasks]:
            try:
                parents.append(_task_from_payload(self._get_json(token, f"/task/{parent_id}")))
            except (requests.RequestException, ValueError, KeyError, TypeError):
                continue
        return parents

    def _team_ids(self, token: str) -> list[str]:
        if self._resolved_team_ids:
            return self._resolved_team_ids
        payload = self._get_json(token, "/team")
        teams = payload.get("teams", [])
        if not teams:
            raise ValueError("ClickUp team_id is required when no authorized Workspace is returned")
        self._resolved_team_ids = [str(teams[0]["id"])]
        return self._resolved_team_ids

    def _assignee_ids(self, token: str) -> list[str]:
        if self._resolved_assignee_ids:
            return self._resolved_assignee_ids
        payload = self._get_json(token, "/user")
        self._resolved_assignee_ids = [str(payload["user"]["id"])]
        return self._resolved_assignee_ids

    def _get_json(self, token: str, path: str, params: list[tuple[str, str]] | None = None) -> dict[str, Any]:
        response = requests.get(
            f"{self.api_base_url}{path}",
            headers={"Authorization": token},
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("ClickUp API returned an unexpected payload")
        return payload


def _task_from_payload(item: dict[str, Any]) -> TaskItem:
    status = item.get("status")
    list_info = item.get("list")
    parent = item.get("parent")
    status_name = str(status.get("status") if isinstance(status, dict) else status or "")
    return TaskItem(
        provider="clickup",
        id=str(item.get("id") or ""),
        title=str(item.get("name") or "Untitled task"),
        status=status_name,
        due_at=_datetime_from_millis(item.get("due_date")),
        url=str(item.get("url") or ""),
        group=str(list_info.get("name") if isinstance(list_info, dict) else ""),
        parent_id=str(parent.get("id") if isinstance(parent, dict) else parent or ""),
        assignee=_assignee_label(item.get("assignees")),
        column=status_name,
    )


def _order_parent_tasks_with_subtasks(tasks: list[TaskItem]) -> list[TaskItem]:
    task_ids = {task.id for task in tasks}
    children_by_parent: dict[str, list[TaskItem]] = {}
    top_level: list[TaskItem] = []
    for task in tasks:
        if task.parent_id and task.parent_id in task_ids:
            children_by_parent.setdefault(task.parent_id, []).append(task)
        else:
            top_level.append(task)

    ordered: list[TaskItem] = []
    for task in sorted(top_level, key=_task_sort_key):
        ordered.append(task)
        ordered.extend(sorted(children_by_parent.get(task.id, []), key=_task_sort_key))
    return ordered


def _task_sort_key(task: TaskItem):
    return (task.due_at or datetime.max.replace(tzinfo=timezone.utc), task.title.lower(), task.id)


def _datetime_from_millis(value: object) -> datetime | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        millis = int(str(value))
    except ValueError:
        return None
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).astimezone()


def _bool_param(value: bool) -> str:
    return "true" if value else "false"


def _ids_from_config(value: list[str] | tuple[str, ...] | str | None, fallback: str = "") -> list[str]:
    raw_items: list[object]
    if isinstance(value, str):
        raw_items = value.split(",")
    elif value is None:
        raw_items = []
    else:
        raw_items = list(value)
    ids = [str(item).strip() for item in raw_items if str(item).strip()]
    if not ids and fallback:
        ids = [fallback]
    return ids


def _assignee_label(value: object) -> str:
    if not isinstance(value, list):
        return ""
    names = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("username") or item.get("email") or item.get("id") or "").strip()
        if name:
            names.append(name)
    return ", ".join(names[:2])
