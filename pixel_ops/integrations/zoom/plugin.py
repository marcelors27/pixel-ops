from __future__ import annotations

from pixel_ops.events.event_bus import EventBus
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution
from pixel_ops.integrations.zoom.client import ZoomApiClient, ZoomPollingRunner
from pixel_ops.integrations.zoom.gateway import ZoomBusEventSource
from pixel_ops.integrations.zoom.participants import ZoomCompanionSource, ZoomParticipantTracker


class ZoomIntegrationPlugin:
    name = "zoom"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.plugin_enabled(self.name, "PIXEL_OPS_ZOOM_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        cfg = ctx.plugin_config(self.name)
        bus = EventBus(maxlen=int(ctx.config.get("integrations", {}).get("social_bus_limit", ctx.env_int("PIXEL_OPS_SOCIAL_BUS_LIMIT", 128))))
        tracker = ZoomParticipantTracker(
            focus_user_id=str(cfg.get("focus_user_id") or ctx.env_value("PIXEL_OPS_ZOOM_FOCUS_USER_ID", "") or ""),
            max_companions=max(0, min(30, int(cfg.get("max_companions", ctx.env_int("PIXEL_OPS_ZOOM_MAX_COMPANIONS", 8))))),
        )
        client = ZoomApiClient(
            account_id=ctx.env_value(str(cfg.get("account_id_env", "PIXEL_OPS_ZOOM_ACCOUNT_ID")), "") or "",
            client_id=ctx.env_value(str(cfg.get("client_id_env", "PIXEL_OPS_ZOOM_CLIENT_ID")), "") or "",
            client_secret=ctx.env_value(str(cfg.get("client_secret_env", "PIXEL_OPS_ZOOM_CLIENT_SECRET")), "") or "",
            api_base_url=str(cfg.get("api_base_url", "https://api.zoom.us/v2")),
            auth_base_url=str(cfg.get("auth_base_url", "https://zoom.us")),
            timeout_seconds=int(cfg.get("timeout_seconds", ctx.env_int("PIXEL_OPS_ZOOM_TIMEOUT_SECONDS", 8))),
            page_size=int(cfg.get("page_size", ctx.env_int("PIXEL_OPS_ZOOM_PAGE_SIZE", 30))),
        )
        runner = ZoomPollingRunner(
            client,
            tracker,
            bus,
            poll_seconds=int(cfg.get("poll_seconds", ctx.env_int("PIXEL_OPS_ZOOM_POLL_SECONDS", 30))),
        )
        return IntegrationContribution(
            event_sources=[ZoomBusEventSource(bus, enabled=True)],
            companion_source=ZoomCompanionSource(tracker),
            starters=[runner.start],
            closers=[runner.stop],
        )


def plugin() -> ZoomIntegrationPlugin:
    return ZoomIntegrationPlugin()
