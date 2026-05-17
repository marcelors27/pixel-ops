from __future__ import annotations

from pathlib import Path

from pixel_ops.events.calendar_events import CalendarEventSource
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution


class IcsIntegrationPlugin:
    name = "ics"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.env_bool("PIXEL_OPS_ICS_ENABLED", False) or bool(getattr(ctx.args, "ics", None))

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        poll_seconds = ctx.env_int("PIXEL_OPS_ICS_POLL_SECONDS", 300)
        sources: list[CalendarEventSource] = []
        paths: list[Path] = []
        arg_path = getattr(ctx.args, "ics", None)
        if arg_path:
            path = Path(arg_path).expanduser()
            sources.append(CalendarEventSource(enabled=True, path=path, poll_seconds=poll_seconds))
            if path.exists():
                paths.append(path)
        for raw_path in ctx.split_env_list(ctx.env_value("PIXEL_OPS_ICS_PATH", "") or ""):
            path = Path(raw_path).expanduser()
            sources.append(CalendarEventSource(enabled=True, path=path, poll_seconds=poll_seconds))
            if path.exists():
                paths.append(path)
        return IntegrationContribution(event_sources=sources, calendar_paths=paths)


def plugin() -> IcsIntegrationPlugin:
    return IcsIntegrationPlugin()
