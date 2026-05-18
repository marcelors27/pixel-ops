from __future__ import annotations

from pixel_ops.data_sources.weather import OpenMeteoWeatherSource
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution


class WeatherIntegrationPlugin:
    name = "weather"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.plugin_enabled(self.name, "PIXEL_OPS_WEATHER_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        cfg = ctx.plugin_config(self.name)
        source = OpenMeteoWeatherSource(
            enabled=True,
            city=str(cfg.get("city") or ctx.env_value("PIXEL_OPS_WEATHER_CITY", "Porto Alegre") or "Porto Alegre"),
            country_code=str(cfg.get("country_code") or ctx.env_value("PIXEL_OPS_WEATHER_COUNTRY", "BR") or "BR"),
            poll_seconds=int(cfg.get("poll_seconds", ctx.env_int("PIXEL_OPS_WEATHER_POLL_SECONDS", 900))),
        )
        return IntegrationContribution(weather_source=source)


def plugin() -> WeatherIntegrationPlugin:
    return WeatherIntegrationPlugin()
