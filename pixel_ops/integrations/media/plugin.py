from __future__ import annotations

from pixel_ops.data_sources.media import LocalMediaSource
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution


class MediaIntegrationPlugin:
    name = "media"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.plugin_enabled(self.name, "PIXEL_OPS_MEDIA_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        cfg = ctx.plugin_config(self.name)
        providers = cfg.get("providers")
        source = LocalMediaSource(
            enabled=True,
            providers=providers if isinstance(providers, list) else ["spotify"],
            poll_seconds=int(cfg.get("poll_seconds", ctx.env_int("PIXEL_OPS_MEDIA_POLL_SECONDS", 10))),
            timeout_seconds=int(cfg.get("timeout_seconds", ctx.env_int("PIXEL_OPS_MEDIA_TIMEOUT_SECONDS", 2))),
            cache_dir=ctx.root_dir / str(cfg.get("cache_dir", "pixel_ops/cache/media_thumbnails")),
        )
        return IntegrationContribution(media_source=source)


def plugin() -> MediaIntegrationPlugin:
    return MediaIntegrationPlugin()
