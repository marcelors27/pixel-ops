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
        self.assertEqual([task.id for task in snapshot.tasks], ["soon", "late"])
        self.assertEqual(snapshot.tasks[0].title, "Soon task")
        self.assertEqual(get.call_args.kwargs["headers"], {"Authorization": "token"})
        self.assertIn(("assignees[]", "user"), get.call_args.kwargs["params"])

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


if __name__ == "__main__":
    unittest.main()
