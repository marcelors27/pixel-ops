from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

from pixel_ops.integration_plugins.async_sources import AsyncEventSource, run_background
from pixel_ops.integration_plugins.base import (
    IntegrationContext,
    IntegrationContribution,
)


PLUGIN_MODULES = {
    "kite": "pixel_ops.integrations.kite.plugin",
    "slack": "pixel_ops.integrations.slack.plugin",
    "discord": "pixel_ops.integrations.discord.plugin",
    "zoom": "pixel_ops.integrations.zoom.plugin",
    "github": "pixel_ops.integrations.github.plugin",
    "google_calendar": "pixel_ops.integrations.google_calendar.plugin",
    "ics": "pixel_ops.integrations.ics.plugin",
    "weather": "pixel_ops.integrations.weather.plugin",
    "ai_usage": "pixel_ops.integrations.ai_usage.plugin",
    "pc_stats": "pixel_ops.integrations.pc_stats.plugin",
    "clickup": "pixel_ops.integrations.clickup.plugin",
    "todoist": "pixel_ops.integrations.todoist.plugin",
    "capacities": "pixel_ops.integrations.capacities.plugin",
    "media": "pixel_ops.integrations.media.plugin",
    "crosshero": "pixel_ops.integrations.crosshero.plugin",
}

PLUGIN_ENABLES = {
    "kite": "PIXEL_OPS_KITE_ENABLED",
    "slack": "PIXEL_OPS_SLACK_ENABLED",
    "discord": "PIXEL_OPS_DISCORD_ENABLED",
    "zoom": "PIXEL_OPS_ZOOM_ENABLED",
    "github": "PIXEL_OPS_GITHUB_ENABLED",
    "google_calendar": "PIXEL_OPS_GOOGLE_CALENDAR_ENABLED",
    "ics": "PIXEL_OPS_ICS_ENABLED",
    "weather": "PIXEL_OPS_WEATHER_ENABLED",
    "ai_usage": "PIXEL_OPS_AI_USAGE_ENABLED",
    "pc_stats": "PIXEL_OPS_PC_STATS_ENABLED",
    "clickup": "PIXEL_OPS_CLICKUP_ENABLED",
    "todoist": "PIXEL_OPS_TODOIST_ENABLED",
    "capacities": "PIXEL_OPS_CAPACITIES_ENABLED",
    "media": "PIXEL_OPS_MEDIA_ENABLED",
    "crosshero": "PIXEL_OPS_CROSSHERO_ENABLED",
}


@dataclass
class IntegrationRuntime:
    event_sources: list = field(default_factory=list)
    calendar_paths: list[Path] = field(default_factory=list)
    starters: list = field(default_factory=list)
    warmers: list = field(default_factory=list)
    closers: list = field(default_factory=list)
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
    runtime.event_sources.extend(AsyncEventSource(source) for source in contribution.event_sources)
    runtime.calendar_paths.extend(contribution.calendar_paths)
    runtime.starters.extend(contribution.starters)
    runtime.warmers.extend(run_background(warmer, f"{warmer}") for warmer in contribution.warmers)
    runtime.closers.extend(contribution.closers)
