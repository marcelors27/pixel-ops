from pixel_ops.data_sources.codex_status import CodexStatusSource
from pixel_ops.events.observation_sources import ObservationEventSource
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution


class CodexStatusIntegrationPlugin:
    name = "codex_status"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.plugin_enabled(self.name, "PIXEL_OPS_CODEX_STATUS_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        cfg = ctx.plugin_config(self.name)
        source = CodexStatusSource(
            socket_path=str(cfg.get("socket_path") or ""),
            thread_id=str(cfg.get("thread_id") or ""),
            poll_seconds=float(cfg.get("poll_seconds", 2)),
            timeout_seconds=float(cfg.get("timeout_seconds", 4)),
        )
        return IntegrationContribution(event_sources=[ObservationEventSource("ai.activity_updated", self.name, source)])


def plugin() -> CodexStatusIntegrationPlugin:
    return CodexStatusIntegrationPlugin()
