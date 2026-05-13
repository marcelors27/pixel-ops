from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

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
        self.token = token or os.environ.get("PIXEL_OPS_GITHUB_TOKEN") or os.environ.get("POKEMON_DASHBOARD_GITHUB_TOKEN", "")
        self.repos = repos or []
        self.poll_seconds = poll_seconds
        self.max_pull_requests = max_pull_requests
        self._last_poll_at: datetime | None = None
        self._pull_requests: list[PullRequestSummary] = []
        self._pending_events: list[WorkEvent] = []
        self._seen: set[str] = set()

    def poll(self, now: datetime) -> list[WorkEvent]:
        self._refresh(now)
        events = self._pending_events
        self._pending_events = []
        return events

    def open_pull_requests(self, now: datetime | None = None) -> list[PullRequestSummary]:
        if now:
            self._refresh(now)
        return list(self._pull_requests)

    def _refresh(self, now: datetime) -> None:
        if not self.enabled or not self.token or not self.repos:
            return
        if self._last_poll_at and (now - self._last_poll_at).total_seconds() < self.poll_seconds:
            return

        previous_poll_at = self._last_poll_at
        self._last_poll_at = now
        pull_requests = self._fetch_open_pull_requests()
        self._pull_requests = pull_requests[: self.max_pull_requests]

        for pr in self._pull_requests:
            key = f"{pr.repo}#{pr.number}"
            if key in self._seen:
                continue
            self._seen.add(key)
            self._pending_events.append(
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
        since = previous_poll_at or now - timedelta(seconds=self.poll_seconds)
        self._pending_events.extend(self._fetch_closed_pull_request_events(now, since))

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

    def _fetch_closed_pull_request_events(self, now: datetime, since: datetime) -> list[WorkEvent]:
        events: list[WorkEvent] = []
        for repo in self.repos:
            encoded_repo = urllib.parse.quote(repo, safe="/")
            url = (
                f"https://api.github.com/repos/{encoded_repo}/pulls"
                f"?state=closed&sort=updated&direction=desc&per_page={self.max_pull_requests}"
            )
            short_repo = repo.split("/")[-1]
            try:
                for item in self._request_json(url):
                    closed_at = self._parse_github_datetime(item.get("closed_at"))
                    if closed_at is None or closed_at <= since:
                        continue
                    number = int(item["number"])
                    title = str(item["title"])
                    author = str(item.get("user", {}).get("login", "unknown"))
                    merged = bool(item.get("merged_at"))
                    state = "merged" if merged else "closed"
                    key = f"{short_repo}#{number}:{state}"
                    if key in self._seen:
                        continue
                    self._seen.add(key)
                    events.append(
                        WorkEvent(
                            category=EventCategory.MERGE if merged else EventCategory.PR_CLOSED,
                            title=f"{short_repo} #{number} {state}",
                            detail=title,
                            priority=EventPriority.MEDIUM,
                            source="github",
                            repo=short_repo,
                            actor=author,
                            external_id=key,
                            occurred_at=closed_at.astimezone(now.tzinfo),
                            metadata={"state": state},
                        )
                    )
            except (urllib.error.URLError, KeyError, ValueError, TypeError):
                continue
        return events

    @staticmethod
    def _parse_github_datetime(value: object) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)

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
