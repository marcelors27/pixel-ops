from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from pixel_ops.data_sources.clickup import ClickUpTaskSource


class ClickUpTaskSourceTests(unittest.TestCase):
    def test_fetches_assigned_tasks_sorted_by_due_date(self):
        due_late = int(datetime(2026, 6, 3, 12, tzinfo=timezone.utc).timestamp() * 1000)
        due_soon = int(datetime(2026, 6, 1, 12, tzinfo=timezone.utc).timestamp() * 1000)
        response = Mock()
        response.json.return_value = {
            "tasks": [
                {"id": "late", "name": "Later task", "status": {"status": "open"}, "due_date": str(due_late), "url": "https://app.clickup.com/t/late"},
                {"id": "soon", "name": "Soon task", "status": {"status": "open"}, "due_date": str(due_soon), "url": "https://app.clickup.com/t/soon"},
                {"id": "nodue", "name": "No due", "status": {"status": "open"}, "due_date": None},
            ]
        }
        response.raise_for_status.return_value = None

        with patch.dict("os.environ", {"PIXEL_OPS_CLICKUP_TOKEN": "token"}), patch("pixel_ops.data_sources.clickup.requests.get", return_value=response) as get:
            source = ClickUpTaskSource(team_id="team", assignee_id="user", max_tasks=3, poll_seconds=1)
            snapshot = source.current(datetime(2026, 5, 31, 12, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.provider, "clickup")
        self.assertEqual([task.id for task in snapshot.tasks], ["soon", "late", "nodue"])
        self.assertEqual(snapshot.tasks[0].title, "Soon task")
        self.assertEqual(get.call_args.kwargs["headers"], {"Authorization": "token"})
        self.assertIn(("assignees[]", "user"), get.call_args.kwargs["params"])
        self.assertFalse(any(name.startswith("due_date_") for name, _value in get.call_args.kwargs["params"]))

    def test_can_exclude_undated_tasks_with_clickup_due_date_filter(self):
        response = Mock()
        response.json.return_value = {
            "tasks": [
                {"id": "nodue", "name": "No due", "status": {"status": "open"}, "due_date": None},
            ]
        }
        response.raise_for_status.return_value = None

        with patch.dict("os.environ", {"PIXEL_OPS_CLICKUP_TOKEN": "token"}), patch("pixel_ops.data_sources.clickup.requests.get", return_value=response) as get:
            source = ClickUpTaskSource(team_id="team", assignee_id="user", include_undated=False, max_tasks=3, poll_seconds=1)
            snapshot = source.current(datetime(2026, 5, 31, 12, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.tasks, ())
        params = get.call_args.kwargs["params"]
        self.assertTrue(any(name == "due_date_lt" for name, _value in params))

    def test_places_subtasks_below_parent_tasks(self):
        due_parent = int(datetime(2026, 6, 3, 12, tzinfo=timezone.utc).timestamp() * 1000)
        due_child = int(datetime(2026, 6, 1, 12, tzinfo=timezone.utc).timestamp() * 1000)
        due_other = int(datetime(2026, 6, 2, 12, tzinfo=timezone.utc).timestamp() * 1000)
        response = Mock()
        response.json.return_value = {
            "tasks": [
                {"id": "child", "name": "Child subtask", "status": {"status": "open"}, "due_date": str(due_child), "parent": "parent"},
                {"id": "parent", "name": "Parent task", "status": {"status": "open"}, "due_date": str(due_parent)},
                {"id": "other", "name": "Other task", "status": {"status": "open"}, "due_date": str(due_other)},
            ]
        }
        response.raise_for_status.return_value = None

        with patch.dict("os.environ", {"PIXEL_OPS_CLICKUP_TOKEN": "token"}), patch("pixel_ops.data_sources.clickup.requests.get", return_value=response):
            source = ClickUpTaskSource(team_id="team", assignee_id="user", max_tasks=5, poll_seconds=1)
            snapshot = source.current(datetime(2026, 5, 31, 12, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        self.assertEqual([task.id for task in snapshot.tasks], ["other", "parent", "child"])
        self.assertEqual(snapshot.tasks[2].parent_id, "parent")

    def test_fetches_missing_parent_task_context_for_assigned_subtasks(self):
        child_response = Mock()
        child_response.json.return_value = {
            "tasks": [
                {"id": "child", "name": "Child subtask", "status": {"status": "open"}, "due_date": None, "parent": "parent"},
            ]
        }
        child_response.raise_for_status.return_value = None
        parent_response = Mock()
        parent_response.json.return_value = {
            "id": "parent",
            "name": "Parent task",
            "status": {"status": "open"},
            "due_date": None,
        }
        parent_response.raise_for_status.return_value = None

        with patch.dict("os.environ", {"PIXEL_OPS_CLICKUP_TOKEN": "token"}), patch(
            "pixel_ops.data_sources.clickup.requests.get",
            side_effect=[child_response, parent_response],
        ) as get:
            source = ClickUpTaskSource(team_id="team", assignee_id="user", max_tasks=5, poll_seconds=1)
            snapshot = source.current(datetime(2026, 5, 31, 12, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        self.assertEqual([task.id for task in snapshot.tasks], ["parent", "child"])
        self.assertEqual(get.call_args_list[1].args[0], "https://api.clickup.com/api/v2/task/parent")

    def test_resolves_current_user_and_first_workspace_when_ids_are_omitted(self):
        team_response = Mock()
        team_response.json.return_value = {"teams": [{"id": "team"}]}
        team_response.raise_for_status.return_value = None
        user_response = Mock()
        user_response.json.return_value = {"user": {"id": "user"}}
        user_response.raise_for_status.return_value = None
        tasks_response = Mock()
        tasks_response.json.return_value = {"tasks": []}
        tasks_response.raise_for_status.return_value = None

        with patch.dict("os.environ", {"PIXEL_OPS_CLICKUP_TOKEN": "token"}), patch(
            "pixel_ops.data_sources.clickup.requests.get",
            side_effect=[team_response, user_response, tasks_response],
        ):
            source = ClickUpTaskSource()
            snapshot = source.current(datetime(2026, 5, 31, 12, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.tasks, ())

    def test_fetches_multiple_assignees_across_multiple_workspaces(self):
        response = Mock()
        response.json.return_value = {"tasks": []}
        response.raise_for_status.return_value = None

        with patch.dict("os.environ", {"PIXEL_OPS_CLICKUP_TOKEN": "token"}), patch("pixel_ops.data_sources.clickup.requests.get", return_value=response) as get:
            source = ClickUpTaskSource(team_ids=["team-a", "team-b"], assignee_ids=["user-a", "user-b"], max_tasks=5, poll_seconds=1)
            snapshot = source.current(datetime(2026, 5, 31, 12, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.tasks, ())
        urls = [call.args[0] for call in get.call_args_list]
        self.assertEqual(urls, ["https://api.clickup.com/api/v2/team/team-a/task", "https://api.clickup.com/api/v2/team/team-b/task"])
        params = get.call_args_list[0].kwargs["params"]
        self.assertIn(("assignees[]", "user-a"), params)
        self.assertIn(("assignees[]", "user-b"), params)


if __name__ == "__main__":
    unittest.main()
