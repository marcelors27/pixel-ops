from __future__ import annotations

from pixel_ops.data_sources.pc_stats import DEFAULT_FIELDS, PCStatsSource
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution


class PCStatsIntegrationPlugin:
    name = "pc_stats"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.plugin_enabled(self.name, "PIXEL_OPS_PC_STATS_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        cfg = ctx.plugin_config(self.name)
        fields = cfg.get("fields", DEFAULT_FIELDS)
        if not isinstance(fields, list):
            fields = list(DEFAULT_FIELDS)
        source = PCStatsSource(
            enabled=True,
            fields=[str(item) for item in fields],
            poll_seconds=int(cfg.get("poll_seconds", ctx.env_int("PIXEL_OPS_PC_STATS_POLL_SECONDS", 5))),
            top_process_count=int(cfg.get("top_process_count", 1)),
            disk_path=str(cfg.get("disk_path") or "/"),
        )
        return IntegrationContribution(pc_stats_source=source)


def plugin() -> PCStatsIntegrationPlugin:
    return PCStatsIntegrationPlugin()
