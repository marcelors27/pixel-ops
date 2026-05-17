from __future__ import annotations

from pixel_ops.events.github_events import GitHubEventSource
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution


class GitHubIntegrationPlugin:
    name = "github"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.env_bool("PIXEL_OPS_GITHUB_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        source = GitHubEventSource(
            enabled=True,
            repos=ctx.split_env_list(ctx.env_value("PIXEL_OPS_GITHUB_REPOS", "") or ""),
            poll_seconds=ctx.env_int("PIXEL_OPS_GITHUB_POLL_SECONDS", 300),
            max_pull_requests=ctx.env_int("PIXEL_OPS_GITHUB_MAX_PRS", 4),
            fetch_pull_requests=ctx.env_int("PIXEL_OPS_GITHUB_FETCH_PRS", 20),
            timeout_seconds=ctx.env_int("PIXEL_OPS_GITHUB_TIMEOUT_SECONDS", 20),
        )
        return IntegrationContribution(event_sources=[source], pull_request_source=source)


def plugin() -> GitHubIntegrationPlugin:
    return GitHubIntegrationPlugin()
