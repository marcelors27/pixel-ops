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
        assignee_id: str = "",
        poll_seconds: int = 120,
        max_tasks: int = 5,
        due_within_days: int = 14,
        include_overdue: bool = True,
        include_subtasks: bool = True,
        include_closed: bool = False,
        timeout_seconds: int = 10,
        api_base_url: str = CLICKUP_API_BASE_URL,
    ):
        self.enabled = enabled
        self.token_env = token_env
        self.team_id = str(team_id or "").strip()
        self.assignee_id = str(assignee_id or "").strip()
        self.poll_seconds = max(1, int(poll_seconds))
        self.max_tasks = max(1, int(max_tasks))
        self.due_within_days = max(1, int(due_within_days))
        self.include_overdue = include_overdue
        self.include_subtasks = include_subtasks
        self.include_closed = include_closed
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.api_base_url = api_base_url.rstrip("/")
        self._last_poll_at: datetime | None = None
        self._snapshot: TaskSnapshot | None = None
        self._resolved_team_id: str | None = self.team_id or None
        self._resolved_assignee_id: str | None = self.assignee_id or None

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
        team_id = self._team_id(token)
        assignee_id = self._assignee_id(token)
        params: list[tuple[str, str]] = [
            ("assignees[]", assignee_id),
            ("include_closed", _bool_param(self.include_closed)),
            ("subtasks", _bool_param(self.include_subtasks)),
            ("order_by", "due_date"),
            ("reverse", "false"),
            ("page", "0"),
        ]
        due_lt = int((now.timestamp() + self.due_within_days * 86400) * 1000)
        params.append(("due_date_lt", str(due_lt)))
        if not self.include_overdue:
            params.append(("due_date_gt", str(int(now.timestamp() * 1000))))
        payload = self._get_json(token, f"/team/{team_id}/task", params=params)
        tasks = [_task_from_payload(item) for item in payload.get("tasks", []) if isinstance(item, dict)]
        tasks = [task for task in tasks if task.due_at is not None]
        tasks.sort(key=lambda task: task.due_at or datetime.max.replace(tzinfo=timezone.utc))
        return tasks[: self.max_tasks]

    def _team_id(self, token: str) -> str:
        if self._resolved_team_id:
            return self._resolved_team_id
        payload = self._get_json(token, "/team")
        teams = payload.get("teams", [])
        if not teams:
            raise ValueError("ClickUp team_id is required when no authorized Workspace is returned")
        self._resolved_team_id = str(teams[0]["id"])
        return self._resolved_team_id

    def _assignee_id(self, token: str) -> str:
        if self._resolved_assignee_id:
            return self._resolved_assignee_id
        payload = self._get_json(token, "/user")
        self._resolved_assignee_id = str(payload["user"]["id"])
        return self._resolved_assignee_id

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
    return TaskItem(
        provider="clickup",
        id=str(item.get("id") or ""),
        title=str(item.get("name") or "Untitled task"),
        status=str(status.get("status") if isinstance(status, dict) else status or ""),
        due_at=_datetime_from_millis(item.get("due_date")),
        url=str(item.get("url") or ""),
        group=str(list_info.get("name") if isinstance(list_info, dict) else ""),
    )


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
