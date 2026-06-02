from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from pixel_ops.data_sources.todoist import TodoistTaskSource


class TodoistTaskSourceTests(unittest.TestCase):
    def test_fetches_tasks_with_project_and_section_columns(self):
        projects_response = Mock()
        projects_response.json.return_value = [{"id": "project", "name": "Work"}]
        projects_response.raise_for_status.return_value = None
        sections_response = Mock()
        sections_response.json.return_value = [{"id": "section", "name": "Doing"}]
        sections_response.raise_for_status.return_value = None
        tasks_response = Mock()
        tasks_response.json.return_value = [
            {
                "id": "task",
                "content": "Ship task HUD",
                "project_id": "project",
                "section_id": "section",
                "due": {"datetime": "2026-06-01T15:00:00Z"},
                "url": "https://todoist.com/showTask?id=task",
            }
        ]
        tasks_response.raise_for_status.return_value = None

        with patch.dict("os.environ", {"PIXEL_OPS_TODOIST_TOKEN": "token"}), patch(
            "pixel_ops.data_sources.todoist.requests.get",
            side_effect=[projects_response, sections_response, tasks_response],
        ) as get:
            source = TodoistTaskSource(project_ids=["project"], max_tasks=5, poll_seconds=1)
            snapshot = source.current(datetime(2026, 5, 31, 12, tzinfo=timezone.utc))

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.provider, "todoist")
        self.assertEqual(snapshot.tasks[0].title, "Ship task HUD")
        self.assertEqual(snapshot.tasks[0].group, "Work")
        self.assertEqual(snapshot.tasks[0].column, "Doing")
        self.assertEqual(get.call_args_list[-1].kwargs["headers"], {"Authorization": "Bearer token"})
        self.assertEqual(get.call_args_list[-1].kwargs["params"], [("project_id", "project")])


if __name__ == "__main__":
    unittest.main()
