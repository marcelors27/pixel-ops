from __future__ import annotations

from pixel_ops.data_sources.crosshero import CrossHeroDaySource
from pixel_ops.events.observation_sources import ObservationEventSource
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution


class CrossHeroIntegrationPlugin:
    name = "crosshero"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.plugin_enabled(self.name, "PIXEL_OPS_CROSSHERO_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        cfg = ctx.plugin_config(self.name)
        source = CrossHeroDaySource(
            box_env=str(cfg.get("box_env") or "PIXEL_OPS_CROSSHERO_BOX"),
            token_env=str(cfg.get("token_env") or "PIXEL_OPS_CROSSHERO_ACCESS_TOKEN"),
            session_cookie_env=str(cfg.get("session_cookie_env") or "PIXEL_OPS_CROSSHERO_SESSION_COOKIE"),
            dashboard_url=str(cfg.get("dashboard_url") or "https://crosshero.com/dashboard/classes"),
            workout_url=str(cfg.get("workout_url") or ""),
            classes_url=str(cfg.get("classes_url") or ""),
            poll_seconds=int(cfg.get("poll_seconds", 300)),
            timeout_seconds=int(cfg.get("timeout_seconds", 10)),
            env_path=ctx.root_dir / ".env",
        )
        return IntegrationContribution(event_sources=[ObservationEventSource("fitness.crosshero_day_updated", "crosshero", source)])


def plugin() -> CrossHeroIntegrationPlugin:
    return CrossHeroIntegrationPlugin()
