from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AIActivityTask:
    """Opaque task identity and lifecycle only; no conversation content."""

    task_id: str
    state: str
    reason: str


@dataclass(frozen=True)
class AIActivitySnapshot:
    """Provider-neutral activity, without conversation content."""

    provider: str
    state: str  # processing, attention, ready, unknown
    reason: str
    observed_at: datetime
    processing: int = 0
    attention: int = 0
    ready: int = 0
    tasks: tuple[AIActivityTask, ...] = ()
