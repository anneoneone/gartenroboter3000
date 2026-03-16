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


@dataclass
class BMP280TemperatureReading:
    """BMP280 temperature reading."""

    temperature_celsius: float
    is_warning: bool
    timestamp: datetime


@dataclass
class BMP280PressureReading:
    """BMP280 air pressure reading."""

    pressure_hpa: float
    altitude_m: float | None
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


class BMP280Sensor:
    """Reads temperature and pressure from GY BMP280 sensor via I2C."""

    def __init__(self, settings: SensorSettings) -> None:
        self.settings = settings
        self._sensor = None
        self._i2c = None
        self._is_available = False

        self._init_sensor()

    def _init_sensor(self) -> None:
        """Initialize I2C and BMP280 sensor."""
        try:
            import board
            import busio
            from adafruit_bmp280 import Adafruit_BMP280_I2C

            # Initialize I2C
            i2c = busio.I2C(board.SCL, board.SDA)
            
            # Get I2C address from settings (default 0x77)
            i2c_address = getattr(self.settings, 'bmp280_i2c_address', 0x77)
            
            # Initialize BMP280 sensor
            self._sensor = Adafruit_BMP280_I2C(i2c, address=i2c_address)
            self._i2c = i2c
            self._is_available = True
            
            logger.info("BMP280 sensor initialized at address 0x%02x", i2c_address)
        except ImportError:
            logger.warning(
                "adafruit-circuitpython-bmp280 not installed. "
                "Install with: pip install adafruit-circuitpython-bmp280"
            )
            self._is_available = False
        except Exception as e:
            logger.error("BMP280 initialization failed: %s", e)
            self._is_available = False

    async def read_temperature(self) -> BMP280TemperatureReading:
        """Read temperature from BMP280."""
        if not self._is_available or self._sensor is None:
            # Return mock data for development
            temp = 22.0 + (hash(datetime.now().second) % 5)
            is_warning = temp >= self.settings.bmp280_temp_warning
            return BMP280TemperatureReading(
                temperature_celsius=round(temp, 1),
                is_warning=is_warning,
                timestamp=datetime.now(UTC),
            )

        try:
            temp = self._sensor.temperature
            is_warning = temp >= self.settings.bmp280_temp_warning
            
            return BMP280TemperatureReading(
                temperature_celsius=round(temp, 1),
                is_warning=is_warning,
                timestamp=datetime.now(UTC),
            )
        except Exception as e:
            logger.error("Failed to read BMP280 temperature: %s", e)
            # Return mock data on error
            return BMP280TemperatureReading(
                temperature_celsius=0.0,
                is_warning=False,
                timestamp=datetime.now(UTC),
            )

    async def read_pressure(self) -> BMP280PressureReading:
        """Read pressure and altitude from BMP280."""
        if not self._is_available or self._sensor is None:
            # Return mock data for development
            pressure = 1013.0 + (hash(datetime.now().second) % 20)
            return BMP280PressureReading(
                pressure_hpa=round(pressure, 1),
                altitude_m=None,
                timestamp=datetime.now(UTC),
            )

        try:
            pressure = self._sensor.pressure
            
            # Calculate altitude if sea level pressure is configured
            altitude = None
            sea_level_pressure = getattr(
                self.settings, 'bmp280_sea_level_pressure_hpa', None
            )
            if sea_level_pressure:
                # Barometric formula: h = 44330 * (1 - (P/P0)^(1/5.255))
                altitude = 44330 * (
                    1.0 - pow(pressure / sea_level_pressure, 1.0 / 5.255)
                )
            
            return BMP280PressureReading(
                pressure_hpa=round(pressure, 1),
                altitude_m=round(altitude, 1) if altitude else None,
                timestamp=datetime.now(UTC),
            )
        except Exception as e:
            logger.error("Failed to read BMP280 pressure: %s", e)
            # Return mock data on error
            return BMP280PressureReading(
                pressure_hpa=0.0,
                altitude_m=None,
                timestamp=datetime.now(UTC),
            )

    async def cleanup(self) -> None:
        """Clean up I2C resources."""
        try:
            if self._i2c:
                self._i2c.deinit()
                self._i2c = None
                self._sensor = None
                self._is_available = False
                logger.info("BMP280 sensor cleaned up")
        except Exception as e:
            logger.error("BMP280 cleanup error: %s", e)


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

        # Initialize BMP280 environmental sensor (optional)
        self.bmp280_sensor = BMP280Sensor(settings)

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

    async def read_bmp280_temperature(self) -> BMP280TemperatureReading:
        """Read BMP280 temperature."""
        return await self.bmp280_sensor.read_temperature()

    async def read_bmp280_pressure(self) -> BMP280PressureReading:
        """Read BMP280 pressure and altitude."""
        return await self.bmp280_sensor.read_pressure()

    async def read_all(
        self,
    ) -> tuple[list[SoilMoistureReading], WaterLevelReading, TemperatureReading, BMP280TemperatureReading, BMP280PressureReading]:
        """Read all sensors concurrently."""
        soil_task = self.read_all_soil_moisture()
        water_task = self.read_water_level()
        temp_task = self.read_pi_temperature()
        bmp280_temp_task = self.read_bmp280_temperature()
        bmp280_pressure_task = self.read_bmp280_pressure()

        soil, water, temp, bmp280_temp, bmp280_pressure = await asyncio.gather(
            soil_task, water_task, temp_task, bmp280_temp_task, bmp280_pressure_task
        )
        return soil, water, temp, bmp280_temp, bmp280_pressure
