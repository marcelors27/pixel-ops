from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock, Thread

from pixel_ops.events.base import EventCategory, EventPriority, WorkEvent


@dataclass(frozen=True)
class PullRequestSummary:
    repo: str
    number: int
    title: str
    author: str
    draft: bool = False
    review_state: str = "open"
    updated_at: datetime | None = None

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
        fetch_pull_requests: int | None = None,
        fetch_deployments: bool = True,
        deployment_workflows: list[str] | None = None,
        startup_lookback_seconds: int = 3600,
        timeout_seconds: int = 20,
    ):
        self.enabled = enabled
        self.token = token or os.environ.get("PIXEL_OPS_GITHUB_TOKEN", "")
        self.repos = repos or []
        self.poll_seconds = poll_seconds
        self.max_pull_requests = max_pull_requests
        self.fetch_pull_requests = fetch_pull_requests or max(max_pull_requests, 20)
        self.fetch_deployments = fetch_deployments
        self.deployment_workflows = tuple(name.lower() for name in (deployment_workflows or []) if name)
        self.startup_lookback_seconds = max(self.poll_seconds, int(startup_lookback_seconds))
        self.timeout_seconds = timeout_seconds
        self._last_poll_at: datetime | None = None
        self._last_open_fetch_at: datetime | None = None
        self._open_pull_requests: list[PullRequestSummary] = []
        self._closed_pull_requests: list[PullRequestSummary] = []
        self._pull_requests: list[PullRequestSummary] = []
        self._pending_events: list[WorkEvent] = []
        self._seen: set[str] = set()
        self._lock = Lock()
        self._refresh_running = False
        self.debug = _env_bool("PIXEL_OPS_DEBUG_EVENTS")

    def warm(self) -> None:
        if not self.enabled or not self.token or not self.repos:
            return
        now = datetime.now(timezone.utc)
        since = now - timedelta(seconds=self.startup_lookback_seconds)
        self._refresh_sync(now, since, include_closed=True)

    def poll(self, now: datetime) -> list[WorkEvent]:
        self._refresh(now)
        with self._lock:
            events = self._pending_events
            self._pending_events = []
        return events

    def open_pull_requests(self, now: datetime | None = None) -> list[PullRequestSummary]:
        if now:
            self._refresh_hud(now)
        with self._lock:
            return list(self._pull_requests)

    def _refresh(self, now: datetime) -> None:
        if not self.enabled or not self.token or not self.repos:
            return
        if self._last_poll_at and (now - self._last_poll_at).total_seconds() < self.poll_seconds:
            return

        previous_poll_at = self._last_poll_at
        self._last_poll_at = now
        since = previous_poll_at or now - timedelta(seconds=self.poll_seconds)
        self._start_refresh_worker(now, since, include_closed=True)

    def _refresh_hud(self, now: datetime) -> None:
        if not self.enabled or not self.token or not self.repos:
            return
        if self._last_open_fetch_at and (now - self._last_open_fetch_at).total_seconds() < self.poll_seconds:
            return
        self._last_open_fetch_at = now
        self._start_refresh_worker(now, now - timedelta(seconds=self.poll_seconds), include_closed=False)

    def _start_refresh_worker(self, now: datetime, since: datetime, include_closed: bool) -> None:
        with self._lock:
            if self._refresh_running:
                return
            self._refresh_running = True
            self._last_open_fetch_at = now

        def worker() -> None:
            try:
                self._refresh_sync(now, since, include_closed)
            finally:
                with self._lock:
                    self._refresh_running = False

    def _refresh_sync(self, now: datetime, since: datetime, include_closed: bool) -> None:
        open_pull_requests = self._fetch_open_pull_requests()
        closed_pull_requests: list[PullRequestSummary] = []
        closed_events: list[WorkEvent] = []
        deployment_events: list[WorkEvent] = []
        if include_closed:
            closed_pull_requests, closed_events = self._fetch_closed_pull_request_updates(now, since)
            deployment_events = self._fetch_deployment_events(now, since)
        with self._lock:
            self._open_pull_requests = open_pull_requests
            if include_closed:
                self._closed_pull_requests = closed_pull_requests
            combined = [*open_pull_requests, *self._closed_pull_requests]
            self._pull_requests = combined[: self.max_pull_requests]
            self._debug(
                f"prs open={len(open_pull_requests)} closed={len(self._closed_pull_requests)} "
                f"hud={len(self._pull_requests)}"
            )
            self._queue_open_pull_request_events(open_pull_requests, now)
            self._pending_events.extend(closed_events)
            self._pending_events.extend(deployment_events)

    def _refresh_open_pull_requests(self, now: datetime) -> list[PullRequestSummary]:
        if self._last_open_fetch_at and (now - self._last_open_fetch_at).total_seconds() < self.poll_seconds:
            return list(self._open_pull_requests)
        self._last_open_fetch_at = now
        self._open_pull_requests = self._fetch_open_pull_requests()
        return list(self._open_pull_requests)

    def _fetch_open_pull_requests(self) -> list[PullRequestSummary]:
        pull_requests: list[PullRequestSummary] = []
        for repo in self.repos:
            encoded_repo = urllib.parse.quote(repo, safe="/")
            url = f"https://api.github.com/repos/{encoded_repo}/pulls?state=open&sort=created&direction=desc&per_page={self.fetch_pull_requests}"
            try:
                for item in self._request_json(url):
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
            except (urllib.error.URLError, KeyError, ValueError, TypeError) as error:
                self._debug(f"open_prs error repo={repo}: {type(error).__name__}: {error}")
                continue
        return pull_requests

    def _queue_open_pull_request_events(self, pull_requests: list[PullRequestSummary], now: datetime) -> None:
        for pr in pull_requests:
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
            self._debug(f"queued {self._pending_events[-1].category.value} {key}")

    def _fetch_closed_pull_request_updates(
        self,
        now: datetime,
        since: datetime,
    ) -> tuple[list[PullRequestSummary], list[WorkEvent]]:
        summaries: list[PullRequestSummary] = []
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
                    if closed_at is None:
                        continue
                    number = int(item["number"])
                    title = str(item["title"])
                    author = str(item.get("user", {}).get("login", "unknown"))
                    merged = bool(item.get("merged_at"))
                    state = "merged" if merged else "closed"
                    summaries.append(
                        PullRequestSummary(
                            repo=short_repo,
                            number=number,
                            title=title,
                            author=author,
                            draft=False,
                            review_state=state,
                            updated_at=closed_at,
                        )
                    )
                    if closed_at <= since:
                        continue
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
            except (urllib.error.URLError, KeyError, ValueError, TypeError) as error:
                self._debug(f"closed_prs error repo={repo}: {type(error).__name__}: {error}")
                continue
        summaries.sort(key=lambda item: item.updated_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return summaries[: self.fetch_pull_requests], events

    def _fetch_deployment_events(self, now: datetime, since: datetime) -> list[WorkEvent]:
        if not self.fetch_deployments:
            return []
        events: list[WorkEvent] = []
        for repo in self.repos:
            encoded_repo = urllib.parse.quote(repo, safe="/")
            short_repo = repo.split("/")[-1]
            url = f"https://api.github.com/repos/{encoded_repo}/actions/runs?per_page=10"
            try:
                payload = self._request_json(url)
                for item in payload.get("workflow_runs", []):
                    updated_at = self._parse_github_datetime(item.get("updated_at"))
                    if updated_at is None or updated_at <= since:
                        continue
                    workflow = str(item.get("name") or "workflow")
                    if self.deployment_workflows and workflow.lower() not in self.deployment_workflows:
                        continue
                    status = str(item.get("status") or "").lower()
                    conclusion = str(item.get("conclusion") or "").lower()
                    category = self._workflow_category(status, conclusion)
                    if category is None:
                        continue
                    run_id = str(item.get("id") or item.get("run_number") or workflow)
                    state = conclusion or status
                    key = f"{short_repo}:workflow:{run_id}:{state}"
                    if key in self._seen:
                        continue
                    self._seen.add(key)
                    events.append(
                        WorkEvent(
                            category=category,
                            title=f"{workflow} {self._workflow_title_state(category)}",
                            detail=short_repo,
                            priority=EventPriority.HIGH if category == EventCategory.BUILD_BROKEN else EventPriority.MEDIUM,
                            source="github",
                            repo=short_repo,
                            external_id=key,
                            occurred_at=updated_at.astimezone(now.tzinfo),
                            metadata={"workflow": workflow, "state": state},
                        )
                    )
                    self._debug(f"queued workflow category={category.value} key={key}")
            except (urllib.error.URLError, KeyError, ValueError, TypeError, AttributeError) as error:
                self._debug(f"workflow_runs error repo={repo}: {type(error).__name__}: {error}")
                continue
        return events

    @staticmethod
    def _workflow_category(status: str, conclusion: str) -> EventCategory | None:
        if status in ("queued", "in_progress", "requested", "pending", "waiting"):
            return EventCategory.DEPLOY_STARTED
        if conclusion == "success":
            return EventCategory.DEPLOY_COMPLETED
        if conclusion in ("failure", "cancelled", "timed_out", "action_required", "startup_failure"):
            return EventCategory.BUILD_BROKEN
        return None

    @staticmethod
    def _workflow_title_state(category: EventCategory) -> str:
        if category == EventCategory.DEPLOY_STARTED:
            return "is deploying"
        if category == EventCategory.DEPLOY_COMPLETED:
            return "deployed"
        return "needs attention"

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
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def _debug(self, message: str) -> None:
        if self.debug:
            print(f"[pixel-ops github] {message}", file=sys.stderr)


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")
