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
    config: dict[str, Any]
    env_bool: EnvBool
    env_int: EnvInt
    env_value: EnvValue
    split_env_list: SplitList

    def plugin_config(self, name: str) -> dict[str, Any]:
        integrations = self.config.get("integrations", {})
        value = integrations.get(name, {})
        return value if isinstance(value, dict) else {}

    def plugin_enabled(self, name: str, env_name: str, default: bool = False) -> bool:
        cfg = self.plugin_config(name)
        if "enabled" in cfg:
            return bool(cfg["enabled"])
        return self.env_bool(env_name, default)


@dataclass
class IntegrationContribution:
    event_sources: list[EventSource] = field(default_factory=list)
    calendar_paths: list[Path] = field(default_factory=list)
    starters: list[Callable[[], None]] = field(default_factory=list)
    warmers: list[Callable[[], None]] = field(default_factory=list)
    pull_request_source: Any | None = None
    weather_source: Any | None = None
    ai_usage_source: Any | None = None
    pc_stats_source: Any | None = None
    task_source: Any | None = None
    closers: list[Callable[[], None]] = field(default_factory=list)


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


class NullWeatherSource:
    def current(self, now: datetime):
        return None


class NullAIUsageSource:
    def current(self, now: datetime | None = None):
        return None

    def poll(self, now: datetime):
        return []


class NullPCStatsSource:
    def current(self, now: datetime | None = None):
        return None


class NullTaskSource:
    def current(self, now: datetime | None = None):
        return None
