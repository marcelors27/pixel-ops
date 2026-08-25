from __future__ import annotations

from pathlib import Path

from pixel_ops.data_sources.ai_usage import AIUsageSource
from pixel_ops.events.observation_sources import ObservationEventSource
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution


class AIUsageIntegrationPlugin:
    name = "ai_usage"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.plugin_enabled(self.name, "PIXEL_OPS_AI_USAGE_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        cfg = ctx.plugin_config(self.name)
        providers = cfg.get("providers", ["codex", "claude", "openai_api"])
        if not isinstance(providers, list):
            providers = ["codex", "claude", "openai_api"]
        thresholds = cfg.get("thresholds", [75, 90])
        if not isinstance(thresholds, list):
            thresholds = [75, 90]
        admin_key_env = str(cfg.get("openai_admin_key_env", "OPENAI_ADMIN_KEY"))
        source = AIUsageSource(
            enabled=True,
            providers=[str(item) for item in providers],
            poll_seconds=int(cfg.get("poll_seconds", ctx.env_int("PIXEL_OPS_AI_USAGE_POLL_SECONDS", 300))),
            codex_home=Path(str(cfg.get("codex_home") or ctx.env_value("CODEX_HOME", "~/.codex") or "~/.codex")).expanduser(),
            claude_projects_path=Path(str(cfg.get("claude_projects_path") or "~/.claude/projects")).expanduser(),
            openai_admin_key=ctx.env_value(admin_key_env, "") or "",
            openai_api_monthly_budget_usd=float(cfg.get("openai_api_monthly_budget_usd", 0) or 0),
            thresholds=tuple(float(item) for item in thresholds),
            timeout_seconds=int(cfg.get("timeout_seconds", 15)),
        )
        return IntegrationContribution(
            event_sources=[source, ObservationEventSource("ai.usage_updated", "ai_usage", source)]
        )


def plugin() -> AIUsageIntegrationPlugin:
    return AIUsageIntegrationPlugin()
