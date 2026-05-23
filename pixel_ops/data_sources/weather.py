from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from threading import Lock, Thread

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


class BaseWeatherSource:
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
        self._lock = Lock()
        self._refresh_running = False

    def current(self, now: datetime) -> WeatherState | None:
        if not self.enabled:
            return None
        mock_effect = os.environ.get("PIXEL_OPS_WEATHER_MOCK_EFFECT", "").strip().lower()
        if mock_effect:
            return self._mock_weather(now, mock_effect)
        if self._last_poll_at and (now - self._last_poll_at).total_seconds() < self.poll_seconds:
            return self._state
        self._last_poll_at = now
        self._refresh_async(now)
        return self._state

    def _refresh_async(self, now: datetime) -> None:
        with self._lock:
            if self._refresh_running:
                return
            self._refresh_running = True

        def worker() -> None:
            try:
                state = self._fetch_weather(now)
                with self._lock:
                    self._state = state
            except (KeyError, TypeError, ValueError, requests.RequestException):
                return
            finally:
                with self._lock:
                    self._refresh_running = False

        Thread(target=worker, daemon=True).start()

    def _mock_weather(self, now: datetime, effect: str) -> WeatherState:
        weather_code = {
            "clear": 0,
            "partly": 2,
            "cloudy": 3,
            "fog": 45,
            "drizzle": 53,
            "rain": 61,
            "snow": 71,
            "storm": 95,
        }.get(effect, 0)
        effects = (effect,)
        return WeatherState(
            city=self.city,
            temperature_c=18,
            temperature_min_c=14,
            temperature_max_c=22,
            apparent_temperature_c=18,
            precipitation_mm=2.4 if effect in ("drizzle", "rain", "storm") else 0,
            rain_mm=2.4 if effect in ("drizzle", "rain", "storm") else 0,
            snowfall_cm=0.8 if effect == "snow" else 0,
            cloud_cover=92 if effect in ("rain", "cloudy", "snow", "storm") else 45 if effect == "partly" else 20,
            wind_speed_kmh=32 if effect == "wind" else 8,
            wind_gusts_kmh=46 if effect == "wind" else 14,
            weather_code=weather_code,
            effects=effects,
            observed_at=now,
        )

    def _fetch_weather(self, now: datetime) -> WeatherState:
        raise NotImplementedError

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


class OpenMeteoWeatherSource(BaseWeatherSource):
    """Polls Open-Meteo current weather for a configured city."""

    def _fetch_weather(self, now: datetime) -> WeatherState:
        coordinates = self._coordinates or self._fetch_coordinates()
        with self._lock:
            self._coordinates = coordinates
        return self._fetch_weather_for_coordinates(now, coordinates)

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

    def _fetch_weather_for_coordinates(self, now: datetime, coordinates: tuple[float, float]) -> WeatherState:
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


class WttrInWeatherSource(BaseWeatherSource):
    """Polls wttr.in JSON weather for a configured city without an API key."""

    def _fetch_weather(self, now: datetime) -> WeatherState:
        location = ",".join(part for part in (self.city, self.country_code) if part)
        response = requests.get(f"https://wttr.in/{urllib.parse.quote(location)}?format=j1", timeout=self.timeout_seconds)
        response.raise_for_status()
        data = response.json()
        current = data["current_condition"][0]
        daily = (data.get("weather") or [{}])[0]
        temperature = float(current.get("temp_C", 0))
        apparent = float(current.get("FeelsLikeC", temperature))
        precipitation = float(current.get("precipMM", 0))
        snowfall = float(current.get("snowfall_cm", 0) or 0)
        cloud_cover = int(current.get("cloudcover", 0))
        wind_speed = float(current.get("windspeedKmph", 0))
        weather_code = _wttr_to_wmo(int(current.get("weatherCode", 0)), cloud_cover)
        temperature_min = _optional_float(daily.get("mintempC"))
        temperature_max = _optional_float(daily.get("maxtempC"))
        return WeatherState(
            city=self.city,
            temperature_c=temperature,
            temperature_min_c=temperature_min,
            temperature_max_c=temperature_max,
            apparent_temperature_c=apparent,
            precipitation_mm=precipitation,
            rain_mm=precipitation,
            snowfall_cm=snowfall,
            cloud_cover=cloud_cover,
            wind_speed_kmh=wind_speed,
            wind_gusts_kmh=wind_speed,
            weather_code=weather_code,
            effects=self._effects(
                temperature,
                apparent,
                precipitation,
                precipitation,
                snowfall,
                cloud_cover,
                wind_speed,
                wind_speed,
                weather_code,
            ),
            observed_at=now,
        )


class OpenWeatherMapWeatherSource(BaseWeatherSource):
    """Polls OpenWeatherMap current weather using an API key from the environment."""

    def __init__(
        self,
        enabled: bool = True,
        city: str = "Porto Alegre",
        country_code: str = "BR",
        poll_seconds: int = 900,
        timeout_seconds: int = 8,
        api_key_env: str = "OPENWEATHERMAP_API_KEY",
    ):
        super().__init__(enabled, city, country_code, poll_seconds, timeout_seconds)
        self.api_key_env = api_key_env

    def _fetch_weather(self, now: datetime) -> WeatherState:
        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            raise ValueError(f"{self.api_key_env} is required for OpenWeatherMap weather")
        query = urllib.parse.urlencode(
            {
                "q": ",".join(part for part in (self.city, self.country_code) if part),
                "appid": api_key,
                "units": "metric",
            }
        )
        response = requests.get(f"https://api.openweathermap.org/data/2.5/weather?{query}", timeout=self.timeout_seconds)
        response.raise_for_status()
        data = response.json()
        main = data.get("main", {})
        wind = data.get("wind", {})
        clouds = data.get("clouds", {})
        weather = (data.get("weather") or [{}])[0]
        rain = data.get("rain", {})
        snow = data.get("snow", {})
        temperature = float(main.get("temp", 0))
        apparent = float(main.get("feels_like", temperature))
        temperature_min = _optional_float(main.get("temp_min"))
        temperature_max = _optional_float(main.get("temp_max"))
        rain_mm = _optional_float(rain.get("1h")) or _optional_float(rain.get("3h")) or 0.0
        snowfall = _optional_float(snow.get("1h")) or _optional_float(snow.get("3h")) or 0.0
        cloud_cover = int(clouds.get("all", 0))
        wind_speed = float(wind.get("speed", 0)) * 3.6
        wind_gusts = float(wind.get("gust", wind.get("speed", 0))) * 3.6
        weather_code = _openweathermap_to_wmo(int(weather.get("id", 0)), cloud_cover)
        precipitation = rain_mm + snowfall
        return WeatherState(
            city=self.city,
            temperature_c=temperature,
            temperature_min_c=temperature_min,
            temperature_max_c=temperature_max,
            apparent_temperature_c=apparent,
            precipitation_mm=precipitation,
            rain_mm=rain_mm,
            snowfall_cm=snowfall / 10,
            cloud_cover=cloud_cover,
            wind_speed_kmh=wind_speed,
            wind_gusts_kmh=wind_gusts,
            weather_code=weather_code,
            effects=self._effects(
                temperature,
                apparent,
                precipitation,
                rain_mm,
                snowfall / 10,
                cloud_cover,
                wind_speed,
                wind_gusts,
                weather_code,
            ),
            observed_at=now,
        )


def _optional_float(value) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _openweathermap_to_wmo(code: int, cloud_cover: int) -> int:
    if 200 <= code < 300:
        return 95
    if 300 <= code < 400:
        return 53
    if 500 <= code < 600:
        return 61 if code in (500, 501, 520) else 63 if code in (502, 521, 531) else 65
    if 600 <= code < 700:
        return 71
    if code in (701, 711, 721, 741):
        return 45
    if code == 800:
        return 0
    if code == 801:
        return 2
    if 802 <= code < 900:
        return 3
    return 3 if cloud_cover >= 65 else 2 if cloud_cover >= 35 else 0


def _wttr_to_wmo(code: int, cloud_cover: int) -> int:
    if code == 113:
        return 0
    if code == 116:
        return 2
    if code in (119, 122):
        return 3
    if code in (143, 248, 260):
        return 45
    if code in (200, 386, 389, 392, 395):
        return 95
    if code in (179, 182, 185, 227, 230, 317, 320, 323, 326, 329, 332, 335, 338, 350, 362, 365, 368, 371, 374, 377):
        return 71
    if code in (176, 263, 266, 293, 296, 353):
        return 53
    if code in (299, 302, 305, 308, 356, 359):
        return 61
    return 3 if cloud_cover >= 65 else 2 if cloud_cover >= 35 else 0


def build_weather_source(
    provider: str = "open_meteo",
    enabled: bool = True,
    city: str = "Porto Alegre",
    country_code: str = "BR",
    poll_seconds: int = 900,
    timeout_seconds: int = 8,
    api_key_env: str = "OPENWEATHERMAP_API_KEY",
) -> BaseWeatherSource:
    normalized = provider.strip().lower().replace("-", "_")
    if normalized in ("open_meteo", "openmeteo"):
        return OpenMeteoWeatherSource(enabled, city, country_code, poll_seconds, timeout_seconds)
    if normalized in ("wttr", "wttr_in"):
        return WttrInWeatherSource(enabled, city, country_code, poll_seconds, timeout_seconds)
    if normalized in ("openweathermap", "open_weather_map"):
        return OpenWeatherMapWeatherSource(enabled, city, country_code, poll_seconds, timeout_seconds, api_key_env)
    raise ValueError(f"Unsupported weather provider: {provider}")
