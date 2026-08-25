from __future__ import annotations

from pixel_ops.data_sources.clickup import ClickUpTaskSource
from pixel_ops.events.observation_sources import ObservationEventSource
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution


class ClickUpIntegrationPlugin:
    name = "clickup"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.plugin_enabled(self.name, "PIXEL_OPS_CLICKUP_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        cfg = ctx.plugin_config(self.name)
        source = ClickUpTaskSource(
            enabled=True,
            token_env=str(cfg.get("token_env") or ctx.env_value("PIXEL_OPS_CLICKUP_TOKEN_ENV", "PIXEL_OPS_CLICKUP_TOKEN") or "PIXEL_OPS_CLICKUP_TOKEN"),
            team_id=str(cfg.get("team_id") or ctx.env_value("PIXEL_OPS_CLICKUP_TEAM_ID", "") or ""),
            team_ids=cfg.get("team_ids", []),
            assignee_id=str(cfg.get("assignee_id") or ctx.env_value("PIXEL_OPS_CLICKUP_ASSIGNEE_ID", "") or ""),
            assignee_ids=cfg.get("assignee_ids", []),
            poll_seconds=int(cfg.get("poll_seconds", ctx.env_int("PIXEL_OPS_CLICKUP_POLL_SECONDS", 120))),
            max_tasks=int(cfg.get("max_tasks", ctx.env_int("PIXEL_OPS_CLICKUP_MAX_TASKS", 5))),
            due_within_days=int(cfg.get("due_within_days", ctx.env_int("PIXEL_OPS_CLICKUP_DUE_WITHIN_DAYS", 14))),
            include_overdue=bool(cfg.get("include_overdue", True)),
            include_undated=bool(cfg.get("include_undated", True)),
            include_subtasks=bool(cfg.get("include_subtasks", True)),
            include_closed=bool(cfg.get("include_closed", False)),
            timeout_seconds=int(cfg.get("timeout_seconds", ctx.env_int("PIXEL_OPS_CLICKUP_TIMEOUT_SECONDS", 10))),
        )
        return IntegrationContribution(event_sources=[ObservationEventSource("tasks.snapshot_updated", "clickup", source)])


def plugin() -> ClickUpIntegrationPlugin:
    return ClickUpIntegrationPlugin()
