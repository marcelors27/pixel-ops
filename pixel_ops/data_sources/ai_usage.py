from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from pixel_ops.events.base import EventCategory, EventPriority, EventSource, WorkEvent


@dataclass(frozen=True)
class AIUsageGauge:
    provider: str
    label: str
    used_percent: float | None = None
    total_tokens: int | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    requests: int | None = None
    cost_usd: float | None = None
    reset_at: datetime | None = None
    status: str = "ok"
    detail: str = ""


@dataclass(frozen=True)
class AIUsageSnapshot:
    gauges: list[AIUsageGauge] = field(default_factory=list)
    updated_at: datetime | None = None

    @property
    def total_tokens(self) -> int:
        codex_tokens = [gauge.total_tokens or 0 for gauge in self.gauges if gauge.provider == "codex"]
        other_tokens = sum(gauge.total_tokens or 0 for gauge in self.gauges if gauge.provider != "codex")
        return other_tokens + (max(codex_tokens) if codex_tokens else 0)

    @property
    def total_cost_usd(self) -> float:
        return sum(gauge.cost_usd or 0.0 for gauge in self.gauges)

    @property
    def pressure(self) -> float:
        percents = [gauge.used_percent for gauge in self.gauges if gauge.used_percent is not None]
        if percents:
            return max(0.0, min(1.0, max(percents) / 100.0))
        if self.total_tokens <= 0:
            return 0.0
        return max(0.0, min(1.0, self.total_tokens / 250_000))


class NullAIUsageSource:
    def current(self, now: datetime | None = None) -> AIUsageSnapshot | None:
        return None

    def poll(self, now: datetime) -> list[WorkEvent]:
        return []


class AIUsageSource(EventSource):
    """Aggregates local/API AI usage into ambient gauges and threshold events.

    The shape follows the useful CodexBar pattern: provider-specific collectors
    normalize usage into small snapshots. Pixel OPs keeps the display ambient by
    exposing gauges and threshold events, not detailed billing tables.
    """

    def __init__(
        self,
        enabled: bool = False,
        providers: list[str] | None = None,
        poll_seconds: int = 300,
        codex_home: Path | None = None,
        claude_projects_path: Path | None = None,
        openai_admin_key: str = "",
        openai_api_monthly_budget_usd: float = 0.0,
        thresholds: tuple[float, ...] = (75.0, 90.0),
        timeout_seconds: int = 15,
    ):
        self.enabled = enabled
        self.providers = tuple(providers or ("codex", "claude", "openai_api"))
        self.poll_seconds = max(30, int(poll_seconds))
        self.codex_home = codex_home or Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
        self.claude_projects_path = claude_projects_path or Path("~/.claude/projects").expanduser()
        self.openai_admin_key = openai_admin_key
        self.openai_api_monthly_budget_usd = max(0.0, float(openai_api_monthly_budget_usd or 0.0))
        self.thresholds = tuple(sorted(thresholds))
        self.timeout_seconds = timeout_seconds
        self._last_poll_at: datetime | None = None
        self._snapshot: AIUsageSnapshot | None = None
        self._announced_thresholds: dict[str, float] = {}

    def current(self, now: datetime | None = None) -> AIUsageSnapshot | None:
        if not self.enabled:
            return None
        if self._snapshot is None:
            self._snapshot = self._collect(_aware(now or datetime.now()))
        return self._snapshot

    def poll(self, now: datetime) -> list[WorkEvent]:
        if not self.enabled:
            return []
        now = _aware(now)
        if self._last_poll_at and (now - self._last_poll_at).total_seconds() < self.poll_seconds:
            return []
        self._last_poll_at = now
        previous = self._snapshot
        self._snapshot = self._collect(now)
        return self._events_for_snapshot(self._snapshot, previous)

    def _collect(self, now: datetime) -> AIUsageSnapshot:
        now = _aware(now)
        gauges: list[AIUsageGauge] = []
        since = now - timedelta(days=29)
        if "codex" in self.providers:
            gauges.extend(self._codex_gauges(since, now))
        if "claude" in self.providers:
            gauges.extend(self._claude_gauges(since, now))
        if "openai_api" in self.providers:
            gauge = self._openai_api_gauge(now)
            if gauge:
                gauges.append(gauge)
        return AIUsageSnapshot(gauges=gauges, updated_at=now)

    def _events_for_snapshot(self, snapshot: AIUsageSnapshot, previous: AIUsageSnapshot | None) -> list[WorkEvent]:
        events: list[WorkEvent] = []
        previous_tokens = previous.total_tokens if previous else 0
        if snapshot.total_tokens > previous_tokens and previous is not None:
            delta = snapshot.total_tokens - previous_tokens
            if delta >= 25_000:
                events.append(
                    WorkEvent(
                        category=EventCategory.AI_USAGE,
                        title="AI current surged through the grid",
                        detail=f"{delta:,} new tokens observed",
                        priority=EventPriority.MEDIUM,
                        source="ai_usage",
                        metadata={
                            "ai_usage_delta_tokens": str(delta),
                            "dominant_types": "electric,psychic",
                        },
                    )
                )

        for gauge in snapshot.gauges:
            if gauge.used_percent is None:
                continue
            for threshold in self.thresholds:
                key = f"{gauge.provider}:{gauge.label}:{threshold:g}"
                if gauge.used_percent >= threshold and self._announced_thresholds.get(key, 0) < threshold:
                    self._announced_thresholds[key] = threshold
                    events.append(
                        WorkEvent(
                            category=EventCategory.AI_USAGE,
                            title=f"{gauge.label} AI meter reached {threshold:g}%",
                            detail=gauge.detail,
                            priority=EventPriority.HIGH if threshold >= 90 else EventPriority.MEDIUM,
                            source="ai_usage",
                            metadata={
                                "ai_usage_provider": gauge.provider,
                                "ai_usage_label": gauge.label,
                                "ai_usage_percent": f"{gauge.used_percent:.1f}",
                                "dominant_types": "electric,psychic",
                            },
                        )
                    )
        return events

    def _codex_gauges(self, since: datetime, until: datetime) -> list[AIUsageGauge]:
        root = self.codex_home / "sessions"
        roots = [root, self.codex_home / "archived_sessions"]
        rows = _scan_jsonl_roots(roots, since, until, mode="codex")
        status = _scan_codex_rate_limit_status(roots, since, until)
        primary_percent = _active_codex_limit_percent(
            status.primary_percent if status else None,
            status.primary_reset_at if status else None,
            until,
        )
        secondary_percent = _active_codex_limit_percent(
            status.secondary_percent if status else None,
            status.secondary_reset_at if status else None,
            until,
        )
        primary_rows = _rows_since(rows, until - timedelta(hours=5))
        secondary_rows = _rows_since(rows, until - timedelta(days=7))
        return [
            _tokens_gauge(
                "codex",
                "Codex 5H",
                primary_rows,
                used_percent=(
                    primary_percent
                    if primary_percent is not None
                    else 0.0 if primary_rows else None
                ),
                reset_at=status.primary_reset_at if primary_percent is not None and status else None,
                detail_suffix="last 5h",
            ),
            _tokens_gauge(
                "codex",
                "Codex W",
                secondary_rows,
                used_percent=(
                    secondary_percent
                    if secondary_percent is not None
                    else 0.0 if secondary_rows else None
                ),
                reset_at=status.secondary_reset_at if secondary_percent is not None and status else None,
                detail_suffix="last 7d",
            ),
        ]

    def _claude_gauges(self, since: datetime, until: datetime) -> list[AIUsageGauge]:
        rows = _scan_jsonl_roots([self.claude_projects_path], since, until, mode="claude")
        return [_tokens_gauge("claude", "Claude", rows)]

    def _openai_api_gauge(self, now: datetime) -> AIUsageGauge | None:
        if not self.openai_admin_key:
            return None
        try:
            start = _utc_day_start(now - timedelta(days=29))
            end = _utc_day_start(now + timedelta(days=1))
            costs = self._openai_get(
                "https://api.openai.com/v1/organization/costs",
                {
                    "start_time": str(int(start.timestamp())),
                    "end_time": str(int(end.timestamp())),
                    "bucket_width": "1d",
                    "limit": "31",
                    "group_by": "line_item",
                },
            )
            usage = self._openai_get(
                "https://api.openai.com/v1/organization/usage/completions",
                {
                    "start_time": str(int(start.timestamp())),
                    "end_time": str(int(end.timestamp())),
                    "bucket_width": "1d",
                    "limit": "31",
                    "group_by": "model",
                },
            )
        except requests.RequestException as error:
            return AIUsageGauge("openai_api", "OpenAI", status="error", detail=type(error).__name__)

        total_cost = 0.0
        for bucket in costs.get("data", []):
            for result in bucket.get("results", []):
                amount = result.get("amount") or {}
                total_cost += float(amount.get("value") or 0)

        rows: list[_UsageRow] = []
        for bucket in usage.get("data", []):
            day = datetime.fromtimestamp(int(bucket.get("start_time", time.time())), tz=timezone.utc)
            for result in bucket.get("results", []):
                rows.append(
                    _UsageRow(
                        timestamp=day,
                        model=str(result.get("model") or "openai"),
                        input_tokens=_int(result.get("input_tokens")) + _int(result.get("input_audio_tokens")),
                        cached_input_tokens=_int(result.get("input_cached_tokens")),
                        output_tokens=_int(result.get("output_tokens")) + _int(result.get("output_audio_tokens")),
                        requests=_int(result.get("num_model_requests")),
                        cost_usd=0.0,
                    )
                )
        gauge = _tokens_gauge("openai_api", "OpenAI", rows)
        used_percent = None
        if self.openai_api_monthly_budget_usd > 0:
            used_percent = max(0.0, min(100.0, total_cost / self.openai_api_monthly_budget_usd * 100))
        return AIUsageGauge(
            provider=gauge.provider,
            label=gauge.label,
            used_percent=used_percent,
            total_tokens=gauge.total_tokens,
            input_tokens=gauge.input_tokens,
            cached_input_tokens=gauge.cached_input_tokens,
            output_tokens=gauge.output_tokens,
            requests=gauge.requests,
            cost_usd=total_cost,
            status=gauge.status,
            detail=f"${total_cost:.2f} last 30d",
        )

    def _openai_get(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {self.openai_admin_key}", "Accept": "application/json"},
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}


@dataclass(frozen=True)
class _UsageRow:
    timestamp: datetime
    model: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class _CodexRateLimitStatus:
    timestamp: datetime
    primary_percent: float | None = None
    primary_reset_at: datetime | None = None
    secondary_percent: float | None = None
    secondary_reset_at: datetime | None = None


def _scan_jsonl_roots(roots: list[Path], since: datetime, until: datetime, mode: str) -> list[_UsageRow]:
    rows: list[_UsageRow] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            rows.extend(_scan_jsonl_file(path, since, until, mode))
    return rows


def _scan_codex_rate_limit_status(
    roots: list[Path],
    since: datetime,
    until: datetime,
) -> _CodexRateLimitStatus | None:
    latest: _CodexRateLimitStatus | None = None
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            status = _scan_codex_rate_limit_file(path, since, until)
            if status and (latest is None or status.timestamp > latest.timestamp):
                latest = status
    return latest


def _scan_codex_rate_limit_file(path: Path, since: datetime, until: datetime) -> _CodexRateLimitStatus | None:
    latest: _CodexRateLimitStatus | None = None
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                timestamp = _parse_timestamp(data.get("timestamp") or data.get("created_at"))
                if not timestamp or timestamp < since or timestamp > until:
                    continue
                payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
                if data.get("type") != "event_msg" or payload.get("type") != "token_count":
                    continue
                rate_limits = payload.get("rate_limits") if isinstance(payload.get("rate_limits"), dict) else {}
                status = _codex_rate_limit_status(timestamp, rate_limits)
                if status and (latest is None or status.timestamp > latest.timestamp):
                    latest = status
    except OSError:
        return None
    return latest


def _codex_rate_limit_status(timestamp: datetime, rate_limits: dict[str, Any]) -> _CodexRateLimitStatus | None:
    primary = rate_limits.get("primary") if isinstance(rate_limits.get("primary"), dict) else {}
    secondary = rate_limits.get("secondary") if isinstance(rate_limits.get("secondary"), dict) else {}
    primary_percent = _optional_float(primary.get("used_percent")) if primary else None
    secondary_percent = _optional_float(secondary.get("used_percent")) if secondary else None
    if primary_percent is None and secondary_percent is None:
        return None
    return _CodexRateLimitStatus(
        timestamp=timestamp,
        primary_percent=primary_percent,
        primary_reset_at=_timestamp_seconds(primary.get("resets_at")) if primary else None,
        secondary_percent=secondary_percent,
        secondary_reset_at=_timestamp_seconds(secondary.get("resets_at")) if secondary else None,
    )


def _active_codex_limit_percent(percent: float | None, reset_at: datetime | None, now: datetime) -> float | None:
    if percent is None:
        return None
    if reset_at is not None and reset_at <= _aware(now):
        return None
    return percent


def _scan_jsonl_file(path: Path, since: datetime, until: datetime, mode: str) -> list[_UsageRow]:
    rows: list[_UsageRow] = []
    current_model = "unknown"
    previous_totals: tuple[int, int, int] | None = None
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                timestamp = _parse_timestamp(data.get("timestamp") or data.get("created_at"))
                if timestamp and (timestamp < since or timestamp > until):
                    continue
                if mode == "codex":
                    row, current_model, previous_totals = _codex_row(data, timestamp, current_model, previous_totals)
                else:
                    row = _claude_row(data, timestamp)
                if row and row.total_tokens > 0:
                    rows.append(row)
    except OSError:
        return rows
    return rows


def _codex_row(
    data: dict[str, Any],
    timestamp: datetime | None,
    current_model: str,
    previous_totals: tuple[int, int, int] | None,
) -> tuple[_UsageRow | None, str, tuple[int, int, int] | None]:
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    if data.get("type") == "turn_context":
        model = payload.get("model")
        if isinstance(model, str) and model:
            current_model = model
        return None, current_model, previous_totals
    if data.get("type") != "event_msg" or payload.get("type") != "token_count":
        return None, current_model, previous_totals
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    current_model = str(info.get("model") or info.get("model_name") or payload.get("model") or current_model or "codex")
    usage = info.get("last_token_usage") if isinstance(info.get("last_token_usage"), dict) else None
    if usage is None and isinstance(info.get("total_token_usage"), dict):
        total = _usage_tuple(info["total_token_usage"])
        base = previous_totals or (0, 0, 0)
        usage = {
            "input_tokens": max(0, total[0] - base[0]),
            "cached_input_tokens": max(0, total[1] - base[1]),
            "output_tokens": max(0, total[2] - base[2]),
        }
        previous_totals = total
    elif isinstance(info.get("total_token_usage"), dict):
        previous_totals = _usage_tuple(info["total_token_usage"])
    if not usage:
        return None, current_model, previous_totals
    return (
        _UsageRow(
            timestamp=timestamp or datetime.now(timezone.utc),
            model=current_model,
            input_tokens=_int(usage.get("input_tokens")),
            cached_input_tokens=_int(usage.get("cached_input_tokens") or usage.get("cache_read_input_tokens")),
            output_tokens=_int(usage.get("output_tokens")),
            requests=1,
        ),
        current_model,
        previous_totals,
    )


def _claude_row(data: dict[str, Any], timestamp: datetime | None) -> _UsageRow | None:
    usage = _find_usage_dict(data)
    if not usage:
        return None
    model = _find_first_string(data, ("model", "model_name")) or "claude"
    return _UsageRow(
        timestamp=timestamp or datetime.now(timezone.utc),
        model=model,
        input_tokens=_int(usage.get("input_tokens") or usage.get("inputTokens")),
        cached_input_tokens=_int(
            usage.get("cache_read_input_tokens")
            or usage.get("cacheReadInputTokens")
            or usage.get("cache_creation_input_tokens")
            or usage.get("cacheCreationInputTokens")
        ),
        output_tokens=_int(usage.get("output_tokens") or usage.get("outputTokens")),
        requests=1,
    )


def _find_usage_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        keys = set(value.keys())
        if {"input_tokens", "output_tokens"} & keys or {"inputTokens", "outputTokens"} & keys:
            return value
        for item in value.values():
            found = _find_usage_dict(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_usage_dict(item)
            if found:
                return found
    return None


def _find_first_string(value: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(value, dict):
        for key in keys:
            if isinstance(value.get(key), str):
                return value[key]
        for item in value.values():
            found = _find_first_string(item, keys)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_first_string(item, keys)
            if found:
                return found
    return None


def _tokens_gauge(
    provider: str,
    label: str,
    rows: list[_UsageRow],
    used_percent: float | None = None,
    reset_at: datetime | None = None,
    detail_suffix: str = "last 30d",
) -> AIUsageGauge:
    total_input = sum(row.input_tokens for row in rows)
    total_cached = sum(row.cached_input_tokens for row in rows)
    total_output = sum(row.output_tokens for row in rows)
    total_requests = sum(row.requests for row in rows)
    total_tokens = total_input + total_output
    if total_tokens <= 0:
        if used_percent is not None:
            return AIUsageGauge(
                provider=provider,
                label=label,
                used_percent=used_percent,
                reset_at=reset_at,
                status="ok",
                detail=f"Codex status {detail_suffix}",
            )
        return AIUsageGauge(provider=provider, label=label, status="quiet", detail="No recent local usage")
    if used_percent is None:
        used_percent = max(0.0, min(100.0, total_tokens / 250_000 * 100))
    return AIUsageGauge(
        provider=provider,
        label=label,
        used_percent=used_percent,
        total_tokens=total_tokens,
        input_tokens=total_input,
        cached_input_tokens=total_cached,
        output_tokens=total_output,
        requests=total_requests,
        reset_at=reset_at,
        status="ok",
        detail=f"{_compact_number(total_tokens)} tokens {detail_suffix}",
    )


def _rows_since(rows: list[_UsageRow], since: datetime) -> list[_UsageRow]:
    return [row for row in rows if row.timestamp >= since]


def _inferred_codex_pressure(rows: list[_UsageRow], until: datetime, window: timedelta) -> float | None:
    window_tokens = sum(row.total_tokens for row in rows if row.timestamp >= until - window)
    if window_tokens <= 0:
        return None
    daily_buckets: dict[datetime, int] = {}
    for row in rows:
        day = _utc_day_start(row.timestamp)
        daily_buckets[day] = daily_buckets.get(day, 0) + row.total_tokens
    active_days = [tokens for tokens in daily_buckets.values() if tokens > 0]
    if not active_days:
        return None
    mean_daily_tokens = sum(active_days) / len(active_days)
    window_days = max(window.total_seconds() / 86400, 5 / 24)
    high_water = _rolling_high_water(daily_buckets, until, max(1, round(window_days)))
    inferred_ceiling = max(250_000 * window_days, mean_daily_tokens * window_days * 2, high_water * window_days * 1.25)
    return max(0.0, min(100.0, window_tokens / inferred_ceiling * 100))


def _rolling_high_water(daily_buckets: dict[datetime, int], until: datetime, days: int) -> int:
    if days <= 1:
        return max(daily_buckets.values(), default=0)
    end = _utc_day_start(until)
    starts = [end - timedelta(days=offset) for offset in range(0, 30)]
    return max(
        (
            sum(daily_buckets.get(start - timedelta(days=inner), 0) for inner in range(days))
            for start in starts
        ),
        default=0,
    )


def _usage_tuple(value: dict[str, Any]) -> tuple[int, int, int]:
    return (
        _int(value.get("input_tokens")),
        _int(value.get("cached_input_tokens") or value.get("cache_read_input_tokens")),
        _int(value.get("output_tokens")),
    )


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _timestamp_seconds(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    raw = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.astimezone()
    return value


def _utc_day_start(value: datetime) -> datetime:
    current = value.astimezone(timezone.utc)
    return current.replace(hour=0, minute=0, second=0, microsecond=0)


def _compact_number(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}k"
    return str(value)
