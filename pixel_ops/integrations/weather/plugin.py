from __future__ import annotations

from pixel_ops.data_sources.weather import build_weather_source
from pixel_ops.events.observation_sources import ObservationEventSource
from pixel_ops.integration_plugins.base import IntegrationContext, IntegrationContribution


class WeatherIntegrationPlugin:
    name = "weather"

    def enabled(self, ctx: IntegrationContext) -> bool:
        return ctx.plugin_enabled(self.name, "PIXEL_OPS_WEATHER_ENABLED", False)

    def build(self, ctx: IntegrationContext) -> IntegrationContribution:
        cfg = ctx.plugin_config(self.name)
        source = build_weather_source(
            provider=str(cfg.get("provider") or ctx.env_value("PIXEL_OPS_WEATHER_PROVIDER", "open_meteo") or "open_meteo"),
            enabled=True,
            city=str(cfg.get("city") or ctx.env_value("PIXEL_OPS_WEATHER_CITY", "Porto Alegre") or "Porto Alegre"),
            country_code=str(cfg.get("country_code") or ctx.env_value("PIXEL_OPS_WEATHER_COUNTRY", "BR") or "BR"),
            poll_seconds=int(cfg.get("poll_seconds", ctx.env_int("PIXEL_OPS_WEATHER_POLL_SECONDS", 900))),
            timeout_seconds=int(cfg.get("timeout_seconds", ctx.env_int("PIXEL_OPS_WEATHER_TIMEOUT_SECONDS", 8))),
            api_key_env=str(cfg.get("api_key_env") or ctx.env_value("PIXEL_OPS_WEATHER_API_KEY_ENV", "OPENWEATHERMAP_API_KEY") or "OPENWEATHERMAP_API_KEY"),
        )
        return IntegrationContribution(event_sources=[ObservationEventSource("weather.conditions_updated", "weather", source)])


def plugin() -> WeatherIntegrationPlugin:
    return WeatherIntegrationPlugin()
