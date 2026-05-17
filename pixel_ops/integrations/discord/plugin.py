from __future__ import annotations

from pixel_ops.events.event_bus import EventBus
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution
from pixel_ops.integrations.discord.gateway import DiscordBusEventSource


class DiscordIntegrationPlugin:
    name = "discord"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.env_bool("PIXEL_OPS_DISCORD_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        bus = EventBus(maxlen=ctx.env_int("PIXEL_OPS_SOCIAL_BUS_LIMIT", 128))
        return IntegrationContribution(
            event_sources=[DiscordBusEventSource(bus, enabled=True)],
        )


def plugin() -> DiscordIntegrationPlugin:
    return DiscordIntegrationPlugin()
