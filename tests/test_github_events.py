from __future__ import annotations

import http.client
import socket
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

    def test_network_disconnect_does_not_kill_refresh_worker_with_traceback(self):
        source = GitHubEventSource(
            enabled=True,
            token="token",
            repos=["owner/repo"],
            poll_seconds=0,
            fetch_deployments=False,
        )
        source._request_json = lambda _url: (_ for _ in ()).throw(http.client.RemoteDisconnected())
        now = datetime(2026, 5, 26, tzinfo=timezone.utc)

        events = source.poll(now)
        for _ in range(20):
            if not source._refresh_running:
                break
            time.sleep(0.01)

        self.assertEqual(events, [])
        self.assertFalse(source._refresh_running)
        self.assertEqual(source.open_pull_requests(), [])

    def test_socket_timeout_does_not_kill_refresh_worker_with_traceback(self):
        source = GitHubEventSource(
            enabled=True,
            token="token",
            repos=["owner/repo"],
            poll_seconds=0,
            fetch_deployments=True,
        )
        source._request_json = lambda _url: (_ for _ in ()).throw(socket.timeout("timed out"))
        now = datetime(2026, 5, 26, tzinfo=timezone.utc)

        events = source.poll(now)
        for _ in range(20):
            if not source._refresh_running:
                break
            time.sleep(0.01)

        self.assertEqual(events, [])
        self.assertFalse(source._refresh_running)
        self.assertEqual(source.open_pull_requests(), [])

    def test_refresh_worker_swallows_transient_network_errors(self):
        source = GitHubEventSource(
            enabled=True,
            token="token",
            repos=["owner/repo"],
            poll_seconds=0,
            fetch_deployments=True,
        )
        source._refresh_sync = lambda _now, _since, _include_closed: (_ for _ in ()).throw(
            http.client.RemoteDisconnected()
        )
        now = datetime(2026, 5, 26, tzinfo=timezone.utc)

        events = source.poll(now)
        for _ in range(20):
            if not source._refresh_running:
                break
            time.sleep(0.01)

        self.assertEqual(events, [])
        self.assertFalse(source._refresh_running)


if __name__ == "__main__":
    unittest.main()
