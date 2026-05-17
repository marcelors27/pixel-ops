from __future__ import annotations

from pixel_ops.events.event_bus import EventBus
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution
from pixel_ops.integrations.slack.socket_mode import SlackSocketModeClient
from pixel_ops.integrations.slack.source import SlackBusEventSource


class SlackIntegrationPlugin:
    name = "slack"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.env_bool("PIXEL_OPS_SLACK_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        bus = EventBus(maxlen=ctx.env_int("PIXEL_OPS_SOCIAL_BUS_LIMIT", 128))
        client = SlackSocketModeClient(
            bus,
            app_token=ctx.env_value("PIXEL_OPS_SLACK_APP_TOKEN", "") or "",
            bot_token=ctx.env_value("PIXEL_OPS_SLACK_BOT_TOKEN", "") or "",
            bot_user_id=ctx.env_value("PIXEL_OPS_SLACK_BOT_USER_ID", "") or "",
            enabled=True,
            reconnect_seconds=ctx.env_int("PIXEL_OPS_SLACK_SOCKET_RECONNECT_SECONDS", 10),
        )
        return IntegrationContribution(
            event_sources=[SlackBusEventSource(bus, enabled=True)],
            starters=[client.start],
        )


def plugin() -> SlackIntegrationPlugin:
    return SlackIntegrationPlugin()
