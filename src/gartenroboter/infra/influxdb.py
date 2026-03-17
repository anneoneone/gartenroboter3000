"""InfluxDB integration for sensor data and metrics logging."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from influxdb_client import InfluxDBClient as InfluxDBClientLib
from influxdb_client import Point
from influxdb_client.client.write_api import ASYNCHRONOUS

if TYPE_CHECKING:
    from gartenroboter.config.settings import InfluxDBSettings

logger = logging.getLogger(__name__)


class InfluxDBWriter:
    """InfluxDB client for writing sensor metrics and measurements."""

    def __init__(self, settings: InfluxDBSettings) -> None:
        """Initialize InfluxDB client.

        Args:
            settings: InfluxDB configuration
        """
        self.settings = settings
        self.enabled = settings.enabled
        self._client: InfluxDBClientLib | None = None
        self._write_api = None

        if self.enabled:
            try:
                self._client = InfluxDBClientLib(
                    url=settings.url,
                    token=settings.token,
                    org=settings.org,
                    timeout=settings.timeout_seconds * 1000,  # Convert to ms
                )
                self._write_api = self._client.write_api(write_type=ASYNCHRONOUS)
                logger.info(
                    f"InfluxDB client initialized (url={settings.url}, bucket={settings.bucket})"
                )
            except Exception as e:
                logger.error(f"Failed to initialize InfluxDB client: {e}")
                self.enabled = False

    async def write_sensor_metrics(
        self,
        soil_readings: list,
        water_level: float,
        pi_temperature: float,
        bmp280_temp: float | None = None,
        bmp280_pressure: float | None = None,
    ) -> None:
        """Write sensor metrics to InfluxDB.

        Args:
            soil_readings: List of soil moisture readings
            water_level: Water level percentage
            pi_temperature: Raspberry Pi temperature in Celsius
            bmp280_temp: BMP280 air temperature in Celsius (optional)
            bmp280_pressure: BMP280 air pressure in hPa (optional)
        """
        if not self.enabled or self._write_api is None:
            return

        try:
            timestamp = datetime.now(UTC)
            points = []

            # Soil moisture readings
            for reading in soil_readings:
                point = (
                    Point("soil_humidity")
                    .tag("zone_id", reading.zone_id)
                    .field("moisture_percent", reading.moisture_percent)
                    .field("raw_value", reading.raw_value)
                    .field("is_dry", reading.is_dry)
                    .time(timestamp)
                )
                points.append(point)

            # Water level
            points.append(
                Point("watertank_level")
                .field("level_percent", water_level)
                .time(timestamp)
            )

            # Pi temperature
            points.append(
                Point("pi_temperature")
                .field("temperature_celsius", pi_temperature)
                .time(timestamp)
            )

            # BMP280 temperature (if available)
            if bmp280_temp is not None:
                points.append(
                    Point("air_temperature")
                    .field("temperature_celsius", bmp280_temp)
                    .time(timestamp)
                )

            # BMP280 pressure (if available)
            if bmp280_pressure is not None:
                points.append(
                    Point("air_pressure")
                    .field("pressure_hpa", bmp280_pressure)
                    .time(timestamp)
                )

            # Write to InfluxDB asynchronously
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._write_api.write(
                    bucket=self.settings.bucket,
                    record=points,
                ),
            )

            logger.debug(f"Wrote {len(points)} metrics to InfluxDB")

        except Exception as e:
            logger.error(f"Failed to write metrics to InfluxDB: {e}")

    async def write_pump_runtime(
        self,
        duration_seconds: float,
        zone_id: int | None = None,
    ) -> None:
        """Write pump runtime event to InfluxDB.

        Args:
            duration_seconds: Pump runtime in seconds
            zone_id: Zone ID if applicable (optional)
        """
        if not self.enabled or self._write_api is None:
            return

        try:
            timestamp = datetime.now(UTC)
            point = Point("pump_runtime").field("duration_seconds", duration_seconds)

            if zone_id is not None:
                point = point.tag("zone_id", zone_id)

            point = point.time(timestamp)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._write_api.write(
                    bucket=self.settings.bucket,
                    record=[point],
                ),
            )

            logger.debug(f"Wrote pump runtime event ({duration_seconds}s) to InfluxDB")

        except Exception as e:
            logger.error(f"Failed to write pump runtime to InfluxDB: {e}")

    async def close(self) -> None:
        """Close InfluxDB connection."""
        if self._client is not None:
            try:
                self._client.close()
                logger.info("InfluxDB connection closed")
            except Exception as e:
                logger.error(f"Error closing InfluxDB connection: {e}")
