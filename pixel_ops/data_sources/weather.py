from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass
from datetime import datetime

import requests


@dataclass(frozen=True)
class WeatherState:
    city: str
    temperature_c: float
    temperature_min_c: float | None
    temperature_max_c: float | None
    apparent_temperature_c: float
    precipitation_mm: float
    rain_mm: float
    snowfall_cm: float
    cloud_cover: int
    wind_speed_kmh: float
    wind_gusts_kmh: float
    weather_code: int
    effects: tuple[str, ...]
    observed_at: datetime | None = None

    @property
    def primary_effect(self) -> str:
        return self.effects[0] if self.effects else "clear"


class OpenMeteoWeatherSource:
    """Polls Open-Meteo current weather for a configured city."""

    def __init__(
        self,
        enabled: bool = True,
        city: str = "Porto Alegre",
        country_code: str = "BR",
        poll_seconds: int = 900,
        timeout_seconds: int = 8,
    ):
        self.enabled = enabled
        self.city = city
        self.country_code = country_code
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self._last_poll_at: datetime | None = None
        self._coordinates: tuple[float, float] | None = None
        self._state: WeatherState | None = None

    def current(self, now: datetime) -> WeatherState | None:
        if not self.enabled:
            return None
        mock_effect = os.environ.get("PIXEL_OPS_WEATHER_MOCK_EFFECT", "").strip().lower()
        if mock_effect:
            return self._mock_weather(now, mock_effect)
        if self._last_poll_at and (now - self._last_poll_at).total_seconds() < self.poll_seconds:
            return self._state
        self._last_poll_at = now
        try:
            self._coordinates = self._coordinates or self._fetch_coordinates()
            self._state = self._fetch_weather(now, self._coordinates)
        except (KeyError, TypeError, ValueError, requests.RequestException):
            return self._state
        return self._state

    def _mock_weather(self, now: datetime, effect: str) -> WeatherState:
        effects = (effect,)
        return WeatherState(
            city=self.city,
            temperature_c=18,
            temperature_min_c=14,
            temperature_max_c=22,
            apparent_temperature_c=18,
            precipitation_mm=2.4 if effect == "rain" else 0,
            rain_mm=2.4 if effect == "rain" else 0,
            snowfall_cm=0.8 if effect == "snow" else 0,
            cloud_cover=92 if effect in ("rain", "cloudy", "snow") else 20,
            wind_speed_kmh=32 if effect == "wind" else 8,
            wind_gusts_kmh=46 if effect == "wind" else 14,
            weather_code={"rain": 61, "snow": 71, "cloudy": 3}.get(effect, 0),
            effects=effects,
            observed_at=now,
        )

    def _fetch_coordinates(self) -> tuple[float, float]:
        query = urllib.parse.urlencode(
            {
                "name": self.city,
                "count": 1,
                "language": "en",
                "format": "json",
                "countryCode": self.country_code,
            }
        )
        response = requests.get(
            f"https://geocoding-api.open-meteo.com/v1/search?{query}",
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        result = response.json()["results"][0]
        return float(result["latitude"]), float(result["longitude"])

    def _fetch_weather(self, now: datetime, coordinates: tuple[float, float]) -> WeatherState:
        latitude, longitude = coordinates
        query = urllib.parse.urlencode(
            {
                "latitude": latitude,
                "longitude": longitude,
                "current": ",".join(
                    (
                        "temperature_2m",
                        "relative_humidity_2m",
                        "apparent_temperature",
                        "precipitation",
                        "rain",
                        "snowfall",
                        "weather_code",
                        "cloud_cover",
                        "wind_speed_10m",
                        "wind_gusts_10m",
                    )
                ),
                "daily": "temperature_2m_max,temperature_2m_min",
                "forecast_days": 1,
                "timezone": "auto",
            }
        )
        response = requests.get(f"https://api.open-meteo.com/v1/forecast?{query}", timeout=self.timeout_seconds)
        response.raise_for_status()
        data = response.json()
        current = data["current"]
        daily = data.get("daily", {})
        temperature = float(current.get("temperature_2m", 0))
        min_temperatures = daily.get("temperature_2m_min") or []
        max_temperatures = daily.get("temperature_2m_max") or []
        temperature_min = float(min_temperatures[0]) if min_temperatures else None
        temperature_max = float(max_temperatures[0]) if max_temperatures else None
        apparent = float(current.get("apparent_temperature", temperature))
        precipitation = float(current.get("precipitation", 0))
        rain = float(current.get("rain", 0))
        snowfall = float(current.get("snowfall", 0))
        cloud_cover = int(current.get("cloud_cover", 0))
        wind_speed = float(current.get("wind_speed_10m", 0))
        wind_gusts = float(current.get("wind_gusts_10m", wind_speed))
        weather_code = int(current.get("weather_code", 0))
        return WeatherState(
            city=self.city,
            temperature_c=temperature,
            temperature_min_c=temperature_min,
            temperature_max_c=temperature_max,
            apparent_temperature_c=apparent,
            precipitation_mm=precipitation,
            rain_mm=rain,
            snowfall_cm=snowfall,
            cloud_cover=cloud_cover,
            wind_speed_kmh=wind_speed,
            wind_gusts_kmh=wind_gusts,
            weather_code=weather_code,
            effects=self._effects(
                temperature,
                apparent,
                precipitation,
                rain,
                snowfall,
                cloud_cover,
                wind_speed,
                wind_gusts,
                weather_code,
            ),
            observed_at=now,
        )

    @staticmethod
    def _effects(
        temperature: float,
        apparent: float,
        precipitation: float,
        rain: float,
        snowfall: float,
        cloud_cover: int,
        wind_speed: float,
        wind_gusts: float,
        weather_code: int,
    ) -> tuple[str, ...]:
        effects: list[str] = []
        if snowfall > 0 or weather_code in (71, 73, 75, 77, 85, 86):
            effects.append("snow")
        if precipitation > 0 or rain > 0 or weather_code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99):
            effects.append("rain")
        if cloud_cover >= 65 or weather_code in (2, 3, 45, 48):
            effects.append("cloudy")
        if wind_speed >= 24 or wind_gusts >= 34:
            effects.append("wind")
        if apparent <= 8 or temperature <= 10:
            effects.append("cold")
        if apparent >= 32 or temperature >= 30:
            effects.append("hot")
        return tuple(dict.fromkeys(effects))
