"""Sensor reading and monitoring modules."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gartenroboter.config.settings import SensorSettings
    from gartenroboter.infra.gpio import GpioInterface

logger = logging.getLogger(__name__)


@dataclass
class SoilMoistureReading:
    """Soil moisture sensor reading."""

    zone_id: int
    channel: int
    raw_value: int
    moisture_percent: float
    is_dry: bool
    timestamp: datetime


@dataclass
class WaterLevelReading:
    """Water level sensor reading."""

    raw_value: int
    level_percent: float
    distance_cm: float
    is_low: bool
    timestamp: datetime


@dataclass
class TemperatureReading:
    """Pi temperature reading."""

    temperature_celsius: float
    is_warning: bool
    timestamp: datetime


class SoilMoistureSensor:
    """Reads soil moisture from capacitive sensors via ADC."""

    def __init__(
        self,
        gpio: GpioInterface,
        settings: SensorSettings,
        zone_id: int,
        channel: int,
    ) -> None:
        self.gpio = gpio
        self.settings = settings
        self.zone_id = zone_id
        self.channel = channel

    def _normalize_reading(self, raw_value: int) -> float:
        """
        Normalize raw ADC value to percentage.

        Uses calibration values to map raw ADC reading (0-1023) to moisture %.
        Lower raw values = more moisture (capacitive sensors work inverse).
        """
        zone_name = f"zone_{self.zone_id}"
        calibration = self.settings.calibration.get(zone_name, {"min": 300, "max": 700})

        min_val = calibration["min"]
        max_val = calibration["max"]

        # Inverse mapping: lower raw value = higher moisture
        if raw_value <= min_val:
            return 100.0
        if raw_value >= max_val:
            return 0.0

        # Linear interpolation (inverse)
        moisture = 100.0 - ((raw_value - min_val) / (max_val - min_val) * 100.0)
        return round(max(0.0, min(100.0, moisture)), 1)

    async def read(self) -> SoilMoistureReading:
        """Read current soil moisture."""
        raw_value = await self.gpio.read_adc_channel(self.channel)
        moisture_percent = self._normalize_reading(raw_value)
        is_dry = moisture_percent < self.settings.soil_threshold_dry

        return SoilMoistureReading(
            zone_id=self.zone_id,
            channel=self.channel,
            raw_value=raw_value,
            moisture_percent=moisture_percent,
            is_dry=is_dry,
            timestamp=datetime.now(UTC),
        )


class WaterLevelSensor:
    """Reads water level from ultrasonic sensor (HC-SR04)."""

    def __init__(self, gpio: GpioInterface, settings: SensorSettings) -> None:
        self.gpio = gpio
        self.settings = settings

        # Configuration for water tank dimensions
        # Adjust these based on your rain barrel height
        self.tank_height_cm = 100.0  # Height from sensor to bottom
        self.sensor_offset_cm = 5.0  # Distance from sensor to full level

    def _calculate_level_percent(self, distance_cm: float) -> float:
        """
        Calculate water level percentage from distance.

        Args:
            distance_cm: Distance from sensor to water surface

        Returns:
            Water level as percentage (0-100)
        """
        if distance_cm < 0:
            return 0.0

        # Calculate water depth
        water_depth = self.tank_height_cm - distance_cm - self.sensor_offset_cm

        # Convert to percentage
        level_percent = (water_depth / self.tank_height_cm) * 100.0

        return round(max(0.0, min(100.0, level_percent)), 1)

    async def read(self) -> WaterLevelReading:
        """Read current water level."""
        distance_cm = await self.gpio.read_ultrasonic_distance()
        level_percent = self._calculate_level_percent(distance_cm)
        is_low = level_percent < self.settings.water_level_min

        return WaterLevelReading(
            raw_value=int(distance_cm * 10),  # Store as mm
            level_percent=level_percent,
            distance_cm=distance_cm,
            is_low=is_low,
            timestamp=datetime.now(UTC),
        )


class PiTemperatureSensor:
    """Reads Raspberry Pi CPU temperature."""

    def __init__(self, settings: SensorSettings) -> None:
        self.settings = settings
        self._is_pi = self._check_if_pi()

    def _check_if_pi(self) -> bool:
        """Check if running on Raspberry Pi."""
        try:
            subprocess.run(
                ["vcgencmd", "measure_temp"],
                capture_output=True,
                check=True,
                timeout=1,
            )
            return True
        except (FileNotFoundError, subprocess.SubprocessError):
            return False

    async def read(self) -> TemperatureReading:
        """Read current Pi temperature."""
        if self._is_pi:
            temp = await self._read_real_temperature()
        else:
            # Mock temperature for development
            temp = 45.0 + (hash(datetime.now().second) % 10)

        is_warning = temp >= self.settings.pi_temp_warning

        return TemperatureReading(
            temperature_celsius=round(temp, 1),
            is_warning=is_warning,
            timestamp=datetime.now(UTC),
        )

    async def _read_real_temperature(self) -> float:
        """Read temperature from vcgencmd."""
        try:
            process = await asyncio.create_subprocess_exec(
                "vcgencmd",
                "measure_temp",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            # Parse output: "temp=45.0'C"
            output = stdout.decode().strip()
            temp_str = output.split("=")[1].split("'")[0]
            return float(temp_str)
        except Exception as e:
            logger.error("Failed to read Pi temperature: %s", e)
            return 0.0


class SensorManager:
    """Manages all sensors and provides consolidated readings."""

    def __init__(
        self,
        gpio: GpioInterface,
        settings: SensorSettings,
        gpio_settings: object,
    ) -> None:
        self.gpio = gpio
        self.settings = settings

        # Initialize soil moisture sensors for each zone
        self.soil_sensors: list[SoilMoistureSensor] = []
        channels = getattr(gpio_settings, "soil_sensor_channels", [0, 1, 2, 3])
        for zone_id, channel in enumerate(channels, start=1):
            self.soil_sensors.append(
                SoilMoistureSensor(gpio, settings, zone_id, channel)
            )

        # Initialize water level sensor
        self.water_sensor = WaterLevelSensor(gpio, settings)

        # Initialize Pi temperature sensor
        self.temp_sensor = PiTemperatureSensor(settings)

    async def read_all_soil_moisture(self) -> list[SoilMoistureReading]:
        """Read all soil moisture sensors concurrently."""
        tasks = [sensor.read() for sensor in self.soil_sensors]
        return await asyncio.gather(*tasks)

    async def read_water_level(self) -> WaterLevelReading:
        """Read water level."""
        return await self.water_sensor.read()

    async def read_pi_temperature(self) -> TemperatureReading:
        """Read Pi temperature."""
        return await self.temp_sensor.read()

    async def read_all(
        self,
    ) -> tuple[list[SoilMoistureReading], WaterLevelReading, TemperatureReading]:
        """Read all sensors concurrently."""
        soil_task = self.read_all_soil_moisture()
        water_task = self.read_water_level()
        temp_task = self.read_pi_temperature()

        soil, water, temp = await asyncio.gather(soil_task, water_task, temp_task)
        return soil, water, temp
