from __future__ import annotations

from pixel_ops.events.event_bus import EventBus
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution
from pixel_ops.integrations.discord.client import DiscordGatewayClient
from pixel_ops.integrations.discord.companions import DiscordCompanionStore
from pixel_ops.integrations.discord.gateway import DiscordBusEventSource
from pixel_ops.integrations.discord.voice_state import DiscordCompanionSource, DiscordVoiceStateTracker
from pixel_ops.state import PixelOpsStateStore


class DiscordIntegrationPlugin:
    name = "discord"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.plugin_enabled(self.name, "PIXEL_OPS_DISCORD_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        cfg = ctx.plugin_config(self.name)
        bus = EventBus(maxlen=int(ctx.config.get("integrations", {}).get("social_bus_limit", ctx.env_int("PIXEL_OPS_SOCIAL_BUS_LIMIT", 128))))
        bot_token_env = str(cfg.get("bot_token_env", "PIXEL_OPS_DISCORD_BOT_TOKEN"))
        guild_id = str(cfg.get("guild_id") or ctx.env_value("PIXEL_OPS_DISCORD_GUILD_ID", "") or "")
        state_store = PixelOpsStateStore(ctx.root_dir / "pixel_ops/state/pixel_ops.sqlite")
        companion_store = DiscordCompanionStore(
            ctx.root_dir / "pixel_ops/config/discord_people.json",
            state_store=state_store,
        )
        tracker = DiscordVoiceStateTracker(
            guild_id=guild_id,
            focus_user_id=str(cfg.get("focus_user_id") or ctx.env_value("PIXEL_OPS_DISCORD_FOCUS_USER_ID", "") or ""),
            max_companions=max(0, min(30, int(cfg.get("max_companions", ctx.env_int("PIXEL_OPS_DISCORD_MAX_COMPANIONS", 5))))),
            companion_store=companion_store,
        )
        client = DiscordGatewayClient(
            bus,
            tracker,
            token=ctx.env_value(bot_token_env, "") or "",
            guild_id=guild_id,
            bot_user_id=str(cfg.get("bot_user_id") or ctx.env_value("PIXEL_OPS_DISCORD_BOT_USER_ID", "") or ""),
            reconnect_seconds=int(cfg.get("gateway_reconnect_seconds", ctx.env_int("PIXEL_OPS_DISCORD_GATEWAY_RECONNECT_SECONDS", 10))),
            enabled=True,
        )
        return IntegrationContribution(
            event_sources=[DiscordBusEventSource(bus, enabled=True, tracker=tracker)],
            companion_source=DiscordCompanionSource(tracker),
            starters=[client.start],
            closers=[client.stop],
        )


def plugin() -> DiscordIntegrationPlugin:
    return DiscordIntegrationPlugin()
