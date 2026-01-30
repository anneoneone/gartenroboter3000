"""GPIO abstraction layer with mock support for development."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gartenroboter.config.settings import GpioSettings

logger = logging.getLogger(__name__)


@dataclass
class SensorReading:
    """A sensor reading with raw and normalized values."""

    channel: int
    raw_value: int
    normalized_value: float  # 0.0 to 100.0 (percentage)
    timestamp: float


class GpioInterface(ABC):
    """Abstract interface for GPIO operations."""

    @abstractmethod
    async def read_adc_channel(self, channel: int) -> int:
        """Read raw value from ADC channel (0-1023 for 10-bit)."""
        ...

    @abstractmethod
    async def read_ultrasonic_distance(self) -> float:
        """Read distance from ultrasonic sensor in cm."""
        ...

    @abstractmethod
    async def set_relay(self, state: bool) -> None:
        """Set relay state (True = on, False = off)."""
        ...

    @abstractmethod
    def get_relay_state(self) -> bool:
        """Get current relay state."""
        ...

    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup GPIO resources."""
        ...


class RealGpio(GpioInterface):
    """Real GPIO implementation for Raspberry Pi."""

    def __init__(self, settings: GpioSettings) -> None:
        self.settings = settings
        self._relay_state = False
        self._spi: object | None = None
        self._relay: object | None = None
        self._trigger: object | None = None
        self._echo: object | None = None

        self._init_hardware()

    def _init_hardware(self) -> None:
        """Initialize hardware interfaces."""
        try:
            import spidev
            from gpiozero import DigitalInputDevice, DigitalOutputDevice

            # Initialize SPI for MCP3008
            self._spi = spidev.SpiDev()
            self._spi.open(0, 0)  # Bus 0, Device 0 (CE0)
            self._spi.max_speed_hz = 1350000

            # Initialize relay
            self._relay = DigitalOutputDevice(
                self.settings.pump_relay_pin,
                active_high=True,
                initial_value=False,
            )

            # Initialize ultrasonic sensor
            self._trigger = DigitalOutputDevice(
                self.settings.ultrasonic_trigger_pin,
                active_high=True,
                initial_value=False,
            )
            self._echo = DigitalInputDevice(self.settings.ultrasonic_echo_pin)

            logger.info("Hardware GPIO initialized successfully")
        except ImportError as e:
            logger.error("Failed to import GPIO libraries: %s", e)
            raise RuntimeError(
                "GPIO libraries not available. Are you running on a Raspberry Pi?"
            ) from e
        except Exception as e:
            logger.error("Failed to initialize hardware: %s", e)
            raise

    async def read_adc_channel(self, channel: int) -> int:
        """Read raw value from MCP3008 ADC channel."""
        if not 0 <= channel <= 7:
            raise ValueError(f"ADC channel must be 0-7, got {channel}")

        if self._spi is None:
            raise RuntimeError("SPI not initialized")

        # MCP3008 command: start bit, single-ended, channel
        cmd = [1, (8 + channel) << 4, 0]
        response = self._spi.xfer2(cmd)

        # Extract 10-bit value from response
        value = ((response[1] & 3) << 8) + response[2]

        return value

    async def read_ultrasonic_distance(self) -> float:
        """Read distance from HC-SR04 ultrasonic sensor in cm."""
        if self._trigger is None or self._echo is None:
            raise RuntimeError("Ultrasonic sensor not initialized")

        # Send trigger pulse
        self._trigger.on()
        await asyncio.sleep(0.00001)  # 10 microseconds
        self._trigger.off()

        # Wait for echo
        pulse_start = time.time()
        timeout = pulse_start + 0.1  # 100ms timeout

        # Wait for echo to go high
        while not self._echo.is_active:
            if time.time() > timeout:
                logger.warning("Ultrasonic timeout waiting for echo start")
                return -1.0
            pulse_start = time.time()

        # Wait for echo to go low
        pulse_end = time.time()
        while self._echo.is_active:
            if time.time() > timeout:
                logger.warning("Ultrasonic timeout waiting for echo end")
                return -1.0
            pulse_end = time.time()

        # Calculate distance (speed of sound = 34300 cm/s)
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150  # (34300 / 2)

        return round(distance, 1)

    async def set_relay(self, state: bool) -> None:
        """Set pump relay state."""
        if self._relay is None:
            raise RuntimeError("Relay not initialized")

        if state:
            self._relay.on()
        else:
            self._relay.off()

        self._relay_state = state
        logger.debug("Relay set to %s", "ON" if state else "OFF")

    def get_relay_state(self) -> bool:
        """Get current relay state."""
        return self._relay_state

    async def cleanup(self) -> None:
        """Cleanup GPIO resources."""
        if self._spi is not None:
            self._spi.close()
        if self._relay is not None:
            self._relay.off()
            self._relay.close()
        if self._trigger is not None:
            self._trigger.close()
        if self._echo is not None:
            self._echo.close()

        logger.info("GPIO resources cleaned up")


class MockGpio(GpioInterface):
    """Mock GPIO implementation for development/testing."""

    def __init__(self, settings: GpioSettings) -> None:
        self.settings = settings
        self._relay_state = False
        self._mock_adc_values: dict[int, int] = {
            0: 450,  # Zone 1: moderately moist
            1: 650,  # Zone 2: dry
            2: 350,  # Zone 3: wet
            3: 550,  # Zone 4: slightly dry
            4: 512,  # Water level: 50%
        }
        self._mock_distance = 25.0  # 25cm water level

        logger.info("Mock GPIO initialized (development mode)")

    def set_mock_adc_value(self, channel: int, value: int) -> None:
        """Set mock ADC value for testing."""
        self._mock_adc_values[channel] = value

    def set_mock_distance(self, distance: float) -> None:
        """Set mock ultrasonic distance for testing."""
        self._mock_distance = distance

    async def read_adc_channel(self, channel: int) -> int:
        """Read mock ADC value."""
        if not 0 <= channel <= 7:
            raise ValueError(f"ADC channel must be 0-7, got {channel}")

        # Add some random variation to simulate real sensors
        import random

        base_value = self._mock_adc_values.get(channel, 512)
        variation = random.randint(-10, 10)
        value = max(0, min(1023, base_value + variation))

        await asyncio.sleep(0.001)  # Simulate read delay
        return value

    async def read_ultrasonic_distance(self) -> float:
        """Read mock ultrasonic distance."""
        import random

        variation = random.uniform(-0.5, 0.5)
        distance = max(0.0, self._mock_distance + variation)

        await asyncio.sleep(0.01)  # Simulate measurement delay
        return round(distance, 1)

    async def set_relay(self, state: bool) -> None:
        """Set mock relay state."""
        self._relay_state = state
        logger.debug("Mock relay set to %s", "ON" if state else "OFF")
        await asyncio.sleep(0.001)

    def get_relay_state(self) -> bool:
        """Get current relay state."""
        return self._relay_state

    async def cleanup(self) -> None:
        """Cleanup (no-op for mock)."""
        logger.info("Mock GPIO cleanup (no-op)")


def create_gpio(settings: GpioSettings, mock_mode: bool = False) -> GpioInterface:
    """
    Factory function to create appropriate GPIO implementation.

    Args:
        settings: GPIO pin configuration
        mock_mode: Force mock mode even on Pi

    Returns:
        GpioInterface implementation
    """
    if mock_mode:
        logger.info("Using mock GPIO (mock_mode=True)")
        return MockGpio(settings)

    # Try to detect if we're on a Raspberry Pi
    try:
        model = Path("/proc/device-tree/model").read_text()
        if "Raspberry Pi" in model:
            logger.info("Detected Raspberry Pi: %s", model.strip())
            return RealGpio(settings)
    except FileNotFoundError:
        pass

    # Not on Pi, use mock
    logger.info("Not running on Raspberry Pi, using mock GPIO")
    return MockGpio(settings)
