from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol


class EventCategory(str, Enum):
    PULL_REQUEST = "pull_request"
    MEETING = "meeting"
    BUILD_BROKEN = "build_broken"
    DEPLOY_STARTED = "deploy_started"
    DEPLOY_COMPLETED = "deploy_completed"
    REVIEW_REQUESTED = "review_requested"
    MESSAGE_IMPORTANT = "message_important"
    INCIDENT = "incident"
    MERGE = "merge"
    PR_APPROVED = "pr_approved"
    AMBIENT = "ambient"


class EventPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class WorkEvent:
    category: EventCategory
    title: str
    detail: str = ""
    priority: EventPriority = EventPriority.MEDIUM
    source: str = "ambient"
    repo: str | None = None
    actor: str | None = None
    external_id: str | None = None
    occurred_at: datetime | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class EventSource(Protocol):
    def poll(self, now: datetime) -> list[WorkEvent]:
        """Return new events since the last poll."""
