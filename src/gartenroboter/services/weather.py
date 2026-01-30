"""Weather service with OpenWeather API integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

import aiohttp

if TYPE_CHECKING:
    from gartenroboter.config.settings import LocationSettings, WeatherSettings

logger = logging.getLogger(__name__)


@dataclass
class WeatherData:
    """Current weather data."""

    temperature_celsius: float
    humidity_percent: float
    description: str
    icon: str
    wind_speed_ms: float
    clouds_percent: int
    rain_mm_1h: float | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ForecastData:
    """Weather forecast data."""

    time: datetime
    temperature_celsius: float
    humidity_percent: float
    description: str
    pop: float  # Probability of precipitation (0-1)
    rain_mm_3h: float | None = None


@dataclass
class CachedWeather:
    """Cached weather data with expiry."""

    current: WeatherData | None = None
    forecast: list[ForecastData] = field(default_factory=list)
    fetched_at: datetime | None = None
    expires_at: datetime | None = None

    def is_expired(self) -> bool:
        """Check if cache is expired."""
        if self.expires_at is None:
            return True
        return datetime.now(UTC) > self.expires_at


class WeatherService:
    """OpenWeather API client with caching and fallback."""

    BASE_URL = "https://api.openweathermap.org/data/2.5"

    def __init__(
        self,
        settings: WeatherSettings,
        location: LocationSettings,
    ) -> None:
        self.settings = settings
        self.location = location
        self._cache = CachedWeather()
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    def _parse_current_weather(self, data: dict[str, Any]) -> WeatherData:
        """Parse current weather response."""
        main = data.get("main", {})
        weather = data.get("weather", [{}])[0]
        wind = data.get("wind", {})
        clouds = data.get("clouds", {})
        rain = data.get("rain", {})

        return WeatherData(
            temperature_celsius=main.get("temp", 0),
            humidity_percent=main.get("humidity", 0),
            description=weather.get("description", "unknown"),
            icon=weather.get("icon", "01d"),
            wind_speed_ms=wind.get("speed", 0),
            clouds_percent=clouds.get("all", 0),
            rain_mm_1h=rain.get("1h"),
        )

    def _parse_forecast(self, data: dict[str, Any]) -> list[ForecastData]:
        """Parse forecast response."""
        forecasts: list[ForecastData] = []

        for item in data.get("list", []):
            main = item.get("main", {})
            weather = item.get("weather", [{}])[0]
            rain = item.get("rain", {})

            forecasts.append(
                ForecastData(
                    time=datetime.fromtimestamp(item.get("dt", 0), tz=UTC),
                    temperature_celsius=main.get("temp", 0),
                    humidity_percent=main.get("humidity", 0),
                    description=weather.get("description", "unknown"),
                    pop=item.get("pop", 0),
                    rain_mm_3h=rain.get("3h"),
                )
            )

        return forecasts

    async def _fetch_current(self) -> WeatherData:
        """Fetch current weather from API."""
        session = await self._get_session()

        params = {
            "lat": self.location.latitude,
            "lon": self.location.longitude,
            "appid": self.settings.api_key,
            "units": "metric",
        }

        url = f"{self.BASE_URL}/weather"

        async with session.get(url, params=params) as response:
            response.raise_for_status()
            data = await response.json()
            return self._parse_current_weather(data)

    async def _fetch_forecast(self) -> list[ForecastData]:
        """Fetch 5-day forecast from API."""
        session = await self._get_session()

        params = {
            "lat": self.location.latitude,
            "lon": self.location.longitude,
            "appid": self.settings.api_key,
            "units": "metric",
        }

        url = f"{self.BASE_URL}/forecast"

        async with session.get(url, params=params) as response:
            response.raise_for_status()
            data = await response.json()
            return self._parse_forecast(data)

    async def _refresh_cache(self) -> None:
        """Refresh weather cache from API."""
        logger.debug("Refreshing weather cache")

        try:
            current = await self._fetch_current()
            forecast = await self._fetch_forecast()

            now = datetime.now(UTC)
            self._cache = CachedWeather(
                current=current,
                forecast=forecast,
                fetched_at=now,
                expires_at=now + timedelta(seconds=self.settings.cache_ttl_seconds),
            )

            logger.info(
                "Weather cache updated: %.1f°C, %s",
                current.temperature_celsius,
                current.description,
            )

        except Exception as e:
            logger.warning("Failed to refresh weather cache: %s", e)
            # Keep stale cache if available
            if self._cache.current is not None:
                logger.info("Using stale weather cache")

    async def get_current(self) -> WeatherData | None:
        """
        Get current weather.

        Returns cached data if valid, otherwise fetches fresh data.
        Returns None if API fails and no cache available.
        """
        if self._cache.is_expired():
            await self._refresh_cache()

        return self._cache.current

    async def get_forecast(self) -> list[ForecastData]:
        """
        Get weather forecast.

        Returns cached data if valid, otherwise fetches fresh data.
        """
        if self._cache.is_expired():
            await self._refresh_cache()

        return self._cache.forecast

    async def is_rain_expected_today(self) -> bool:
        """
        Check if rain is expected today.

        Uses probability of precipitation (pop) threshold.
        """
        forecast = await self.get_forecast()

        if not forecast:
            return False

        today = datetime.now(UTC).date()

        for item in forecast:
            # Only check today's forecast
            if item.time.date() != today:
                continue

            # Check if high probability of rain
            if item.pop >= 0.5:  # 50% or higher
                logger.debug(
                    "Rain expected at %s: %d%% chance",
                    item.time.strftime("%H:%M"),
                    int(item.pop * 100),
                )
                return True

            # Check if rain amount is significant
            if item.rain_mm_3h and item.rain_mm_3h >= 1.0:
                logger.debug(
                    "Rain expected at %s: %.1fmm",
                    item.time.strftime("%H:%M"),
                    item.rain_mm_3h,
                )
                return True

        return False

    async def get_daily_forecast(self, days: int = 3) -> list[dict]:
        """Get daily weather summary for the next N days.

        Args:
            days: Number of days to forecast (default 3)

        Returns:
            List of daily summaries with date, temp_min, temp_max, description, rain_chance
        """
        forecast = await self.get_forecast()

        if not forecast:
            return []

        # Group forecasts by date
        daily: dict[date, list[ForecastData]] = {}
        for item in forecast:
            d = item.time.date()
            if d not in daily:
                daily[d] = []
            daily[d].append(item)

        # Build daily summaries
        result = []
        sorted_dates = sorted(daily.keys())

        for d in sorted_dates[:days]:
            items = daily[d]
            temps = [i.temperature_celsius for i in items]
            max_pop = max(i.pop for i in items)

            # Get most common description (midday if available)
            midday_items = [i for i in items if 10 <= i.time.hour <= 16]
            desc = midday_items[0].description if midday_items else items[0].description

            result.append(
                {
                    "date": d,
                    "temp_min": min(temps),
                    "temp_max": max(temps),
                    "description": desc,
                    "rain_chance": max_pop,
                }
            )

        return result

    async def get_status_summary(self) -> str:
        """Get human-readable weather status."""
        current = await self.get_current()

        if current is None:
            return "Weather data unavailable"

        rain_str = ""
        if current.rain_mm_1h:
            rain_str = f", Rain: {current.rain_mm_1h:.1f}mm/h"

        return (
            f"{current.temperature_celsius:.1f}°C, "
            f"{current.description}, "
            f"Humidity: {current.humidity_percent}%"
            f"{rain_str}"
        )
