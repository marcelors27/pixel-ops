from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from pixel_ops.events.base import EventCategory, EventPriority, WorkEvent


@dataclass(frozen=True)
class PullRequestSummary:
    repo: str
    number: int
    title: str
    author: str
    draft: bool = False
    review_state: str = "open"

    @property
    def label(self) -> str:
        state = "DRAFT" if self.draft else self.review_state.upper()
        return f"{self.repo} #{self.number} {state}: {self.title}"


class GitHubEventSource:
    """Polls GitHub for open pull requests and keeps a compact HUD list."""

    def __init__(
        self,
        enabled: bool = False,
        token: str | None = None,
        repos: list[str] | None = None,
        poll_seconds: int = 300,
        max_pull_requests: int = 4,
    ):
        self.enabled = enabled
        self.token = token or os.environ.get("PIXEL_OPS_GITHUB_TOKEN", "")
        self.repos = repos or []
        self.poll_seconds = poll_seconds
        self.max_pull_requests = max_pull_requests
        self._last_poll_at: datetime | None = None
        self._pull_requests: list[PullRequestSummary] = []
        self._seen: set[str] = set()

    def poll(self, now: datetime) -> list[WorkEvent]:
        if not self.enabled or not self.token or not self.repos:
            return []
        if self._last_poll_at and (now - self._last_poll_at).total_seconds() < self.poll_seconds:
            return []

        self._last_poll_at = now
        pull_requests = self._fetch_open_pull_requests()
        self._pull_requests = pull_requests[: self.max_pull_requests]

        events: list[WorkEvent] = []
        for pr in self._pull_requests:
            key = f"{pr.repo}#{pr.number}"
            if key in self._seen:
                continue
            self._seen.add(key)
            events.append(
                WorkEvent(
                    category=EventCategory.REVIEW_REQUESTED if not pr.draft else EventCategory.PULL_REQUEST,
                    title=f"{pr.repo} #{pr.number} ready for review",
                    detail=pr.title,
                    priority=EventPriority.MEDIUM,
                    source="github",
                    repo=pr.repo,
                    actor=pr.author,
                    external_id=key,
                    occurred_at=now,
                )
            )
        return events

    def open_pull_requests(self, now: datetime | None = None) -> list[PullRequestSummary]:
        if now:
            self.poll(now)
        return list(self._pull_requests)

    def _fetch_open_pull_requests(self) -> list[PullRequestSummary]:
        pull_requests: list[PullRequestSummary] = []
        for repo in self.repos:
            encoded_repo = urllib.parse.quote(repo, safe="/")
            url = f"https://api.github.com/repos/{encoded_repo}/pulls?state=open&per_page={self.max_pull_requests}"
            try:
                for item in self._request_json(url):
                    if item.get("draft", False):
                        continue
                    pull_requests.append(
                        PullRequestSummary(
                            repo=repo.split("/")[-1],
                            number=int(item["number"]),
                            title=str(item["title"]),
                            author=str(item.get("user", {}).get("login", "unknown")),
                            draft=bool(item.get("draft", False)),
                            review_state="review",
                        )
                    )
            except (urllib.error.URLError, KeyError, ValueError, TypeError):
                continue
        return pull_requests

    def _request_json(self, url: str):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "pixel-ops",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
