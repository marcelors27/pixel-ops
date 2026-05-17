from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution, NullPullRequestSource


PLUGIN_MODULES = {
    "slack": "pixel_ops.integrations.slack.plugin",
    "discord": "pixel_ops.integrations.discord.plugin",
    "github": "pixel_ops.integrations.github.plugin",
    "google_calendar": "pixel_ops.integrations.google_calendar.plugin",
    "ics": "pixel_ops.integrations.ics.plugin",
}

PLUGIN_ENABLES = {
    "slack": "PIXEL_OPS_SLACK_ENABLED",
    "discord": "PIXEL_OPS_DISCORD_ENABLED",
    "github": "PIXEL_OPS_GITHUB_ENABLED",
    "google_calendar": "PIXEL_OPS_GOOGLE_CALENDAR_ENABLED",
    "ics": "PIXEL_OPS_ICS_ENABLED",
}


@dataclass
class IntegrationRuntime:
    event_sources: list = field(default_factory=list)
    calendar_paths: list[Path] = field(default_factory=list)
    starters: list = field(default_factory=list)
    warmers: list = field(default_factory=list)
    pull_request_source: object = field(default_factory=NullPullRequestSource)
    loaded_plugins: list[str] = field(default_factory=list)

    def start(self) -> None:
        for starter in self.starters:
            starter()

    def warm(self) -> None:
        for warmer in self.warmers:
            warmer()


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
        if ctx.env_bool(env_name, False)
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
    if contribution.pull_request_source is not None:
        runtime.pull_request_source = contribution.pull_request_source
