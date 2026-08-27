from __future__ import annotations

from pixel_ops.data_sources.capacities import CapacitiesProjectSource
from pixel_ops.events.observation_sources import ObservationEventSource
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution


class CapacitiesIntegrationPlugin:
    name = "capacities"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.plugin_enabled(self.name, "PIXEL_OPS_CAPACITIES_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        cfg = ctx.plugin_config(self.name)
        source = CapacitiesProjectSource(
            token_env=str(cfg.get("token_env") or "PIXEL_OPS_CAPACITIES_TOKEN"),
            structure_names=cfg.get("structure_names", ["Projeto", "Project"]),
            poll_seconds=int(cfg.get("poll_seconds", 300)),
            max_projects=int(cfg.get("max_projects", 24)),
            timeout_seconds=int(cfg.get("timeout_seconds", 10)),
        )
        # The source keeps its normal API cache, while the adapter checks often
        # enough to recover quickly if the first request fails during startup.
        return IntegrationContribution(
            event_sources=[ObservationEventSource("projects.snapshot_updated", "capacities", source, poll_seconds=min(5, source.poll_seconds))]
        )


def plugin() -> CapacitiesIntegrationPlugin:
    return CapacitiesIntegrationPlugin()
