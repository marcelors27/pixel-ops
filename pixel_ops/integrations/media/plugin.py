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
        youtube_browser_apps = cfg.get("youtube_browser_apps")
        browser_extension = cfg.get("browser_extension", {})
        browser_extension = browser_extension if isinstance(browser_extension, dict) else {}
        source = LocalMediaSource(
            enabled=True,
            providers=providers if isinstance(providers, list) else ["spotify"],
            poll_seconds=int(cfg.get("poll_seconds", ctx.env_int("PIXEL_OPS_MEDIA_POLL_SECONDS", 10))),
            timeout_seconds=int(cfg.get("timeout_seconds", ctx.env_int("PIXEL_OPS_MEDIA_TIMEOUT_SECONDS", 2))),
            cache_dir=ctx.root_dir / str(cfg.get("cache_dir", "pixel_ops/cache/media_thumbnails")),
            youtube_browser_apps=youtube_browser_apps if isinstance(youtube_browser_apps, list) else None,
            browser_extension_host=str(browser_extension.get("host", "127.0.0.1")),
            browser_extension_port=int(browser_extension.get("port", 47832)),
            browser_extension_token=str(browser_extension.get("token", "")),
            browser_extension_stale_seconds=int(browser_extension.get("stale_seconds", 15)),
        )
        return IntegrationContribution(media_source=source, starters=[source.start], closers=[source.close])


def plugin() -> MediaIntegrationPlugin:
    return MediaIntegrationPlugin()
