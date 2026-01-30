"""Sun tracker for sunset/sunrise calculation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import aiohttp

if TYPE_CHECKING:
    from gartenroboter.config.settings import LocationSettings, WeatherSettings

logger = logging.getLogger(__name__)


@dataclass
class SunTimes:
    """Sunrise and sunset times for a day."""

    date: date
    sunrise: datetime
    sunset: datetime
    solar_noon: datetime
    day_length_hours: float
    timezone: str

    def is_after_sunset(self, dt: datetime | None = None) -> bool:
        """Check if given time (or now) is after sunset."""
        if dt is None:
            dt = datetime.now(ZoneInfo(self.timezone))

        # Ensure we're comparing in the same timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(self.timezone))

        return dt >= self.sunset

    def is_before_sunrise(self, dt: datetime | None = None) -> bool:
        """Check if given time (or now) is before sunrise."""
        if dt is None:
            dt = datetime.now(ZoneInfo(self.timezone))

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(self.timezone))

        return dt < self.sunrise

    def is_night(self, dt: datetime | None = None) -> bool:
        """Check if given time (or now) is night (after sunset or before sunrise)."""
        return self.is_after_sunset(dt) or self.is_before_sunrise(dt)


@dataclass
class CachedSunTimes:
    """Cached sun times with expiry."""

    times: SunTimes | None = None
    fetched_at: datetime | None = None

    def is_valid_for_date(self, check_date: date) -> bool:
        """Check if cache is valid for given date."""
        if self.times is None:
            return False
        return self.times.date == check_date


class SunTracker:
    """
    Tracks sunrise and sunset times.

    Uses sunrise-sunset.org API with fallback to approximate calculation.
    Caches results per day to minimize API calls.
    """

    API_URL = "https://api.sunrise-sunset.org/json"

    def __init__(
        self,
        location: LocationSettings,
        weather_settings: WeatherSettings | None = None,
    ) -> None:
        self.location = location
        self.weather_settings = weather_settings
        self._cache = CachedSunTimes()
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

    def _parse_time(self, time_str: str, target_date: date) -> datetime:
        """Parse time string from API (format: 'HH:MM:SS AM/PM')."""
        try:
            # API returns times in UTC
            time_obj = datetime.strptime(time_str, "%I:%M:%S %p").time()
            dt_utc = datetime.combine(target_date, time_obj, tzinfo=UTC)

            # Convert to local timezone
            local_tz = ZoneInfo(self.location.timezone)
            return dt_utc.astimezone(local_tz)
        except ValueError as e:
            logger.warning("Failed to parse time '%s': %s", time_str, e)
            raise

    async def _fetch_from_api(self, target_date: date) -> SunTimes:
        """Fetch sun times from sunrise-sunset.org API."""
        session = await self._get_session()

        params = {
            "lat": self.location.latitude,
            "lng": self.location.longitude,
            "date": target_date.isoformat(),
            "formatted": 1,  # Get formatted time strings
        }

        async with session.get(self.API_URL, params=params) as response:
            response.raise_for_status()
            data = await response.json()

            if data.get("status") != "OK":
                raise ValueError(f"API returned error: {data.get('status')}")

            results = data["results"]

            sunrise = self._parse_time(results["sunrise"], target_date)
            sunset = self._parse_time(results["sunset"], target_date)
            solar_noon = self._parse_time(results["solar_noon"], target_date)

            # Parse day length (format: "HH:MM:SS")
            day_length_parts = results["day_length"].split(":")
            day_length_hours = (
                int(day_length_parts[0])
                + int(day_length_parts[1]) / 60
                + int(day_length_parts[2]) / 3600
            )

            return SunTimes(
                date=target_date,
                sunrise=sunrise,
                sunset=sunset,
                solar_noon=solar_noon,
                day_length_hours=round(day_length_hours, 2),
                timezone=self.location.timezone,
            )

    def _calculate_approximate(self, target_date: date) -> SunTimes:
        """
        Calculate approximate sun times without API.

        Uses a simplified algorithm based on latitude and day of year.
        Not as accurate as API but works offline.
        """
        import math

        local_tz = ZoneInfo(self.location.timezone)
        lat = self.location.latitude

        # Day of year (1-366)
        day_of_year = target_date.timetuple().tm_yday

        # Approximate solar declination (simplified)
        declination = -23.45 * math.cos(math.radians(360 / 365 * (day_of_year + 10)))

        # Hour angle at sunset
        lat_rad = math.radians(lat)
        decl_rad = math.radians(declination)

        try:
            cos_hour_angle = -math.tan(lat_rad) * math.tan(decl_rad)
            cos_hour_angle = max(-1, min(1, cos_hour_angle))  # Clamp for polar regions
            hour_angle = math.degrees(math.acos(cos_hour_angle))
        except ValueError:
            # Polar day/night - use default times
            hour_angle = 90  # 6 hours from noon

        # Calculate times (hours from midnight, solar time)
        solar_noon_hour = 12.0
        sunrise_hour = solar_noon_hour - hour_angle / 15
        sunset_hour = solar_noon_hour + hour_angle / 15

        # Adjust for longitude (rough approximation)
        # Standard timezone meridian offset
        timezone_offset = 15 * round(self.location.longitude / 15)
        longitude_correction = (
            (timezone_offset - self.location.longitude) * 4 / 60
        )  # hours

        sunrise_hour += longitude_correction
        sunset_hour += longitude_correction
        solar_noon_hour += longitude_correction

        # Create datetime objects
        base_dt = datetime.combine(target_date, datetime.min.time(), tzinfo=local_tz)

        sunrise = base_dt + timedelta(hours=sunrise_hour)
        sunset = base_dt + timedelta(hours=sunset_hour)
        solar_noon = base_dt + timedelta(hours=solar_noon_hour)

        day_length_hours = (sunset - sunrise).total_seconds() / 3600

        return SunTimes(
            date=target_date,
            sunrise=sunrise,
            sunset=sunset,
            solar_noon=solar_noon,
            day_length_hours=round(day_length_hours, 2),
            timezone=self.location.timezone,
        )

    async def get_sun_times(self, target_date: date | None = None) -> SunTimes:
        """
        Get sunrise/sunset times for a date.

        Uses cache if available, otherwise fetches from API.
        Falls back to calculation if API fails.

        Args:
            target_date: Date to get times for (default: today)

        Returns:
            SunTimes with sunrise, sunset, and other solar data
        """
        if target_date is None:
            local_tz = ZoneInfo(self.location.timezone)
            target_date = datetime.now(local_tz).date()

        # Check cache
        if self._cache.is_valid_for_date(target_date):
            logger.debug("Using cached sun times for %s", target_date)
            return self._cache.times  # type: ignore

        # Try API first
        try:
            sun_times = await self._fetch_from_api(target_date)
            logger.info(
                "Fetched sun times for %s: sunrise=%s, sunset=%s",
                target_date,
                sun_times.sunrise.strftime("%H:%M"),
                sun_times.sunset.strftime("%H:%M"),
            )
        except Exception as e:
            logger.warning("API fetch failed, using calculation: %s", e)
            sun_times = self._calculate_approximate(target_date)
            logger.info(
                "Calculated sun times for %s: sunrise=%s, sunset=%s",
                target_date,
                sun_times.sunrise.strftime("%H:%M"),
                sun_times.sunset.strftime("%H:%M"),
            )

        # Update cache
        self._cache = CachedSunTimes(
            times=sun_times,
            fetched_at=datetime.now(UTC),
        )

        return sun_times

    async def is_after_sunset(self) -> bool:
        """Check if current time is after sunset."""
        sun_times = await self.get_sun_times()
        return sun_times.is_after_sunset()

    async def is_night(self) -> bool:
        """Check if current time is night (after sunset or before sunrise)."""
        sun_times = await self.get_sun_times()
        return sun_times.is_night()

    async def get_next_sunset(self) -> datetime:
        """Get the next sunset time (today or tomorrow)."""
        local_tz = ZoneInfo(self.location.timezone)
        now = datetime.now(local_tz)

        sun_times = await self.get_sun_times(now.date())

        if now < sun_times.sunset:
            return sun_times.sunset

        # Already past sunset, get tomorrow's
        tomorrow = now.date() + timedelta(days=1)
        sun_times = await self.get_sun_times(tomorrow)
        return sun_times.sunset

    async def get_time_until_sunset(self) -> timedelta:
        """Get time remaining until next sunset."""
        local_tz = ZoneInfo(self.location.timezone)
        now = datetime.now(local_tz)
        next_sunset = await self.get_next_sunset()
        return next_sunset - now

    async def get_next_sunrise(self) -> datetime:
        """Get the next sunrise time (today or tomorrow)."""
        local_tz = ZoneInfo(self.location.timezone)
        now = datetime.now(local_tz)

        sun_times = await self.get_sun_times(now.date())

        if now < sun_times.sunrise:
            return sun_times.sunrise

        # Already past sunrise, get tomorrow's
        tomorrow = now.date() + timedelta(days=1)
        sun_times = await self.get_sun_times(tomorrow)
        return sun_times.sunrise

    async def get_next_sun_event(self) -> tuple[str, datetime]:
        """Get the next sun event (sunrise or sunset, whichever comes first).

        Returns:
            Tuple of (event_name, event_time) where event_name is 'sunrise' or 'sunset'
        """
        next_sunrise = await self.get_next_sunrise()
        next_sunset = await self.get_next_sunset()

        if next_sunrise < next_sunset:
            return ("sunrise", next_sunrise)
        else:
            return ("sunset", next_sunset)
