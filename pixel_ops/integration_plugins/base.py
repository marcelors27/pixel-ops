from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from pixel_ops.events.base import EventSource


EnvBool = Callable[[str, bool], bool]
EnvInt = Callable[[str, int], int]
EnvValue = Callable[[str, Optional[str]], Optional[str]]
SplitList = Callable[[str], list[str]]


@dataclass(frozen=True)
class IntegrationContext:
    root_dir: Path
    args: object
    env_bool: EnvBool
    env_int: EnvInt
    env_value: EnvValue
    split_env_list: SplitList


@dataclass
class IntegrationContribution:
    event_sources: list[EventSource] = field(default_factory=list)
    calendar_paths: list[Path] = field(default_factory=list)
    starters: list[Callable[[], None]] = field(default_factory=list)
    warmers: list[Callable[[], None]] = field(default_factory=list)
    pull_request_source: Any | None = None


class IntegrationPlugin(Protocol):
    name: str

    def enabled(self, ctx: IntegrationContext) -> bool:
        ...

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        ...


class NullPullRequestSource:
    def open_pull_requests(self, now: datetime | None = None):
        return []

    def poll(self, now: datetime):
        return []
