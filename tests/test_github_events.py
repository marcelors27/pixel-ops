from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone

from pixel_ops.events.base import EventCategory
from pixel_ops.events.github_events import GitHubEventSource


class GitHubEventSourceTests(unittest.TestCase):
    def test_poll_starts_refresh_worker_and_emits_open_pull_request_event(self):
        source = GitHubEventSource(
            enabled=True,
            token="token",
            repos=["owner/repo"],
            poll_seconds=0,
            fetch_deployments=False,
        )
        source._request_json = lambda _url: [
            {
                "number": 42,
                "title": "Add ambient PR encounters",
                "user": {"login": "dev"},
                "draft": False,
            }
        ]
        now = datetime(2026, 5, 26, tzinfo=timezone.utc)

        events = []
        for _ in range(20):
            events.extend(source.poll(now))
            if events:
                break
            time.sleep(0.01)

        self.assertFalse(source._refresh_running)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, EventCategory.REVIEW_REQUESTED)
        self.assertEqual(events[0].external_id, "repo#42")


if __name__ == "__main__":
    unittest.main()
