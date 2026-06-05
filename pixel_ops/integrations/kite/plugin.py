from __future__ import annotations

from pixel_ops.events.event_bus import EventBus
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution
from pixel_ops.integrations.kite.source import PixelOpsKiteClient, PixelOpsKiteEventSource
from pixel_ops.integrations.zoom.participants import ZoomCompanionSource, ZoomParticipantTracker


class PixelOpsKiteIntegrationPlugin:
    name = "kite"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.plugin_enabled(self.name, "PIXEL_OPS_KITE_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        cfg = ctx.plugin_config(self.name)
        bus = EventBus(maxlen=int(ctx.config.get("integrations", {}).get("social_bus_limit", ctx.env_int("PIXEL_OPS_SOCIAL_BUS_LIMIT", 128))))
        zoom_cfg = cfg.get("zoom", {}) if isinstance(cfg.get("zoom"), dict) else {}
        zoom_tracker = ZoomParticipantTracker(
            focus_user_id=str(zoom_cfg.get("focus_user_id") or cfg.get("focus_user_id") or ctx.env_value("PIXEL_OPS_KITE_ZOOM_FOCUS_USER_ID", "") or ""),
            max_companions=max(0, min(30, int(zoom_cfg.get("max_companions", cfg.get("max_companions", ctx.env_int("PIXEL_OPS_KITE_MAX_COMPANIONS", 8)))))),
        )
        token_env = str(cfg.get("token_env", "PIXEL_OPS_KITE_TOKEN"))
        client = PixelOpsKiteClient(
            bus,
            ws_url=str(cfg.get("ws_url") or ctx.env_value("PIXEL_OPS_KITE_WS_URL", "") or ""),
            token=ctx.env_value(token_env, "") or "",
            reconnect_seconds=int(cfg.get("reconnect_seconds", ctx.env_int("PIXEL_OPS_KITE_RECONNECT_SECONDS", 10))),
            enabled=True,
            zoom_tracker=zoom_tracker,
        )
        return IntegrationContribution(
            event_sources=[PixelOpsKiteEventSource(bus, enabled=True)],
            companion_source=ZoomCompanionSource(zoom_tracker),
            starters=[client.start],
            closers=[client.stop],
        )


def plugin() -> PixelOpsKiteIntegrationPlugin:
    return PixelOpsKiteIntegrationPlugin()
