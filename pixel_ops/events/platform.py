from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class PixelOpsEventKind(str, Enum):
    FACT = "fact"
    OBSERVATION = "observation"
    LIFECYCLE = "lifecycle"
    CLOCK = "clock"


@dataclass(frozen=True)
class PixelOpsEvent:
    """Provider-neutral input consumed by a selected game engine."""

    type: str
    occurred_at: datetime
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    kind: PixelOpsEventKind = PixelOpsEventKind.OBSERVATION
    subject: str | None = None
    correlation_id: str | None = None
    schema_version: int = 1
    id: str = field(default_factory=lambda: uuid4().hex)

    @classmethod
    def observation(cls, event_type: str, source: str, value: Any, now: datetime) -> "PixelOpsEvent":
        return cls(type=event_type, occurred_at=now, source=source, payload={"value": value})

    @classmethod
    def tick(cls, now: datetime) -> "PixelOpsEvent":
        return cls(
            type="runtime.tick",
            occurred_at=now,
            source="runtime",
            payload={"now": now},
            kind=PixelOpsEventKind.CLOCK,
        )

