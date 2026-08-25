from __future__ import annotations

from pixel_ops.data_sources.todoist import TodoistTaskSource
from pixel_ops.events.observation_sources import ObservationEventSource
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution


class TodoistIntegrationPlugin:
    name = "todoist"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.plugin_enabled(self.name, "PIXEL_OPS_TODOIST_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        cfg = ctx.plugin_config(self.name)
        source = TodoistTaskSource(
            enabled=True,
            token_env=str(cfg.get("token_env") or ctx.env_value("PIXEL_OPS_TODOIST_TOKEN_ENV", "PIXEL_OPS_TODOIST_TOKEN") or "PIXEL_OPS_TODOIST_TOKEN"),
            poll_seconds=int(cfg.get("poll_seconds", ctx.env_int("PIXEL_OPS_TODOIST_POLL_SECONDS", 120))),
            max_tasks=int(cfg.get("max_tasks", ctx.env_int("PIXEL_OPS_TODOIST_MAX_TASKS", 12))),
            due_within_days=int(cfg.get("due_within_days", ctx.env_int("PIXEL_OPS_TODOIST_DUE_WITHIN_DAYS", 14))),
            include_overdue=bool(cfg.get("include_overdue", True)),
            include_undated=bool(cfg.get("include_undated", True)),
            project_ids=cfg.get("project_ids", []),
            section_ids=cfg.get("section_ids", []),
            filter=str(cfg.get("filter") or ctx.env_value("PIXEL_OPS_TODOIST_FILTER", "") or ""),
            timeout_seconds=int(cfg.get("timeout_seconds", ctx.env_int("PIXEL_OPS_TODOIST_TIMEOUT_SECONDS", 10))),
        )
        return IntegrationContribution(event_sources=[ObservationEventSource("tasks.snapshot_updated", "todoist", source)])


def plugin() -> TodoistIntegrationPlugin:
    return TodoistIntegrationPlugin()
