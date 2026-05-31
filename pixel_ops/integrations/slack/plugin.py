from __future__ import annotations

from pixel_ops.events.event_bus import EventBus
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution
from pixel_ops.integrations.slack.activity import SlackAmbientAggregator
from pixel_ops.integrations.slack.socket_mode import SlackSocketModeClient
from pixel_ops.integrations.slack.source import SlackBusEventSource


class SlackIntegrationPlugin:
    name = "slack"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.plugin_enabled(self.name, "PIXEL_OPS_SLACK_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        cfg = ctx.plugin_config(self.name)
        bus = EventBus(maxlen=int(ctx.config.get("integrations", {}).get("social_bus_limit", ctx.env_int("PIXEL_OPS_SOCIAL_BUS_LIMIT", 128))))
        app_token_env = str(cfg.get("app_token_env", "PIXEL_OPS_SLACK_APP_TOKEN"))
        bot_token_env = str(cfg.get("bot_token_env", "PIXEL_OPS_SLACK_BOT_TOKEN"))
        aggregator = SlackAmbientAggregator(
            activity_window_seconds=int(cfg.get("activity_window_seconds", 120)),
            activity_threshold=int(cfg.get("activity_threshold", 5)),
            activity_cooldown_seconds=int(cfg.get("activity_cooldown_seconds", 300)),
            summary_window_seconds=int(cfg.get("summary_window_seconds", 900)),
            channel_rules=SlackAmbientAggregator.rules_from_config(cfg.get("channels", {})),
        )
        client = SlackSocketModeClient(
            bus,
            app_token=ctx.env_value(app_token_env, "") or "",
            bot_token=ctx.env_value(bot_token_env, "") or "",
            bot_user_id=str(cfg.get("bot_user_id") or ctx.env_value("PIXEL_OPS_SLACK_BOT_USER_ID", "") or ""),
            enabled=True,
            reconnect_seconds=int(cfg.get("socket_reconnect_seconds", ctx.env_int("PIXEL_OPS_SLACK_SOCKET_RECONNECT_SECONDS", 10))),
            aggregator=aggregator,
        )
        return IntegrationContribution(
            event_sources=[SlackBusEventSource(bus, enabled=True)],
            starters=[client.start],
            closers=[client.stop],
        )


def plugin() -> SlackIntegrationPlugin:
    return SlackIntegrationPlugin()
