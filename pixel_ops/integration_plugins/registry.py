from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

from pixel_ops.data_sources.tasks import MergedTaskSource
from pixel_ops.integration_plugins.base import (
    IntegrationContext,
    IntegrationContribution,
    NullAIUsageSource,
    NullCompanionSource,
    NullMediaSource,
    NullPCStatsSource,
    NullPullRequestSource,
    NullTaskSource,
    NullWeatherSource,
)


PLUGIN_MODULES = {
    "slack": "pixel_ops.integrations.slack.plugin",
    "discord": "pixel_ops.integrations.discord.plugin",
    "github": "pixel_ops.integrations.github.plugin",
    "google_calendar": "pixel_ops.integrations.google_calendar.plugin",
    "ics": "pixel_ops.integrations.ics.plugin",
    "weather": "pixel_ops.integrations.weather.plugin",
    "ai_usage": "pixel_ops.integrations.ai_usage.plugin",
    "pc_stats": "pixel_ops.integrations.pc_stats.plugin",
    "clickup": "pixel_ops.integrations.clickup.plugin",
    "todoist": "pixel_ops.integrations.todoist.plugin",
    "media": "pixel_ops.integrations.media.plugin",
}

PLUGIN_ENABLES = {
    "slack": "PIXEL_OPS_SLACK_ENABLED",
    "discord": "PIXEL_OPS_DISCORD_ENABLED",
    "github": "PIXEL_OPS_GITHUB_ENABLED",
    "google_calendar": "PIXEL_OPS_GOOGLE_CALENDAR_ENABLED",
    "ics": "PIXEL_OPS_ICS_ENABLED",
    "weather": "PIXEL_OPS_WEATHER_ENABLED",
    "ai_usage": "PIXEL_OPS_AI_USAGE_ENABLED",
    "pc_stats": "PIXEL_OPS_PC_STATS_ENABLED",
    "clickup": "PIXEL_OPS_CLICKUP_ENABLED",
    "todoist": "PIXEL_OPS_TODOIST_ENABLED",
    "media": "PIXEL_OPS_MEDIA_ENABLED",
}


@dataclass
class IntegrationRuntime:
    event_sources: list = field(default_factory=list)
    calendar_paths: list[Path] = field(default_factory=list)
    starters: list = field(default_factory=list)
    warmers: list = field(default_factory=list)
    closers: list = field(default_factory=list)
    pull_request_source: object = field(default_factory=NullPullRequestSource)
    weather_source: object = field(default_factory=NullWeatherSource)
    ai_usage_source: object = field(default_factory=NullAIUsageSource)
    pc_stats_source: object = field(default_factory=NullPCStatsSource)
    task_source: object = field(default_factory=NullTaskSource)
    media_source: object = field(default_factory=NullMediaSource)
    companion_source: object = field(default_factory=NullCompanionSource)
    loaded_plugins: list[str] = field(default_factory=list)

    def start(self) -> None:
        for starter in self.starters:
            starter()

    def warm(self) -> None:
        for warmer in self.warmers:
            warmer()

    def close(self) -> None:
        for closer in reversed(self.closers):
            closer()


def build_integration_runtime(ctx: IntegrationContext) -> IntegrationRuntime:
    runtime = IntegrationRuntime()
    for name in _selected_plugin_names(ctx):
        plugin = _load_plugin(name)
        if not plugin.enabled(ctx):
            continue
        contribution = plugin.build(ctx)
        _merge(runtime, contribution)
        runtime.loaded_plugins.append(plugin.name)
    return runtime


def _selected_plugin_names(ctx: IntegrationContext) -> list[str]:
    names = [
        name
        for name, env_name in PLUGIN_ENABLES.items()
        if ctx.plugin_enabled(name, env_name, False)
    ]
    if bool(getattr(ctx.args, "ics", None)) and "ics" not in names:
        names.append("ics")
    return names


def _load_plugin(name: str):
    module = importlib.import_module(PLUGIN_MODULES[name])
    return module.plugin()


def _merge(runtime: IntegrationRuntime, contribution: IntegrationContribution) -> None:
    runtime.event_sources.extend(contribution.event_sources)
    runtime.calendar_paths.extend(contribution.calendar_paths)
    runtime.starters.extend(contribution.starters)
    runtime.warmers.extend(contribution.warmers)
    runtime.closers.extend(contribution.closers)
    if contribution.pull_request_source is not None:
        runtime.pull_request_source = contribution.pull_request_source
    if contribution.weather_source is not None:
        runtime.weather_source = contribution.weather_source
    if contribution.ai_usage_source is not None:
        runtime.ai_usage_source = contribution.ai_usage_source
    if contribution.pc_stats_source is not None:
        runtime.pc_stats_source = contribution.pc_stats_source
    if contribution.task_source is not None:
        if isinstance(runtime.task_source, NullTaskSource):
            runtime.task_source = contribution.task_source
        elif isinstance(runtime.task_source, MergedTaskSource):
            runtime.task_source.add(contribution.task_source)
        else:
            runtime.task_source = MergedTaskSource([runtime.task_source, contribution.task_source])
    if contribution.media_source is not None:
        runtime.media_source = contribution.media_source
    if contribution.companion_source is not None:
        runtime.companion_source = contribution.companion_source
