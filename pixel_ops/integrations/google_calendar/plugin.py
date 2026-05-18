from __future__ import annotations

from pixel_ops.data_sources.calendar import download_ics
from pixel_ops.events.calendar_events import CalendarEventSource
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution


class GoogleCalendarIntegrationPlugin:
    name = "google_calendar"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.plugin_enabled(self.name, "PIXEL_OPS_GOOGLE_CALENDAR_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        cfg = ctx.plugin_config(self.name)
        poll_seconds = int(cfg.get("poll_seconds", ctx.env_int("PIXEL_OPS_GOOGLE_CALENDAR_POLL_SECONDS", ctx.env_int("PIXEL_OPS_ICS_POLL_SECONDS", 300))))
        urls = list(cfg.get("ics_urls") or ctx.split_env_list(ctx.env_value("PIXEL_OPS_GOOGLE_CALENDAR_ICS_URL", None) or ""))
        sources: list[CalendarEventSource] = []
        cache_paths = []
        warmers = []
        for index, url in enumerate(urls, start=1):
            cache_path = ctx.root_dir / f"pixel_ops/cache/calendar/google_calendar_{index}.ics"
            sources.append(CalendarEventSource(enabled=True, url=url, cache_path=cache_path, poll_seconds=poll_seconds))
            cache_paths.append(cache_path)
            warmers.append(lambda url=url, cache_path=cache_path: download_ics(url, cache_path))
        return IntegrationContribution(event_sources=sources, calendar_paths=cache_paths, warmers=warmers)


def plugin() -> GoogleCalendarIntegrationPlugin:
    return GoogleCalendarIntegrationPlugin()
