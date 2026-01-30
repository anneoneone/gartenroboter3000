"""Pytest configuration and shared fixtures."""

from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gartenroboter.config.settings import Settings
from gartenroboter.infra.gpio import GpioInterface

# ============================================================================
# Mock GPIO
# ============================================================================


class MockGpio(GpioInterface):
    """Mock GPIO interface for testing."""

    def __init__(self) -> None:
        self._adc_values: dict[int, int] = {i: 512 for i in range(8)}
        self._relay_state = False
        self._ultrasonic_distance = 50.0
        self._cleaned_up = False

    async def read_adc_channel(self, channel: int) -> int:
        """Read raw value from ADC channel (0-1023 for 10-bit)."""
        return self._adc_values.get(channel, 512)

    async def read_ultrasonic_distance(self) -> float:
        """Read distance from ultrasonic sensor in cm."""
        return self._ultrasonic_distance

    async def set_relay(self, state: bool) -> None:
        """Set relay state (True = on, False = off)."""
        self._relay_state = state

    def get_relay_state(self) -> bool:
        """Get current relay state."""
        return self._relay_state

    async def cleanup(self) -> None:
        """Cleanup GPIO resources."""
        self._cleaned_up = True
        self._relay_state = False

    # Test helper methods
    def set_spi_value(self, channel: int, value: int) -> None:
        """Set mock ADC value for testing."""
        self._adc_values[channel] = value

    def set_ultrasonic_distance(self, distance: float) -> None:
        """Set mock ultrasonic distance for testing."""
        self._ultrasonic_distance = distance

    @property
    def is_cleaned_up(self) -> bool:
        return self._cleaned_up


@pytest.fixture
def mock_gpio() -> MockGpio:
    """Create mock GPIO interface."""
    return MockGpio()


# ============================================================================
# Mock Settings
# ============================================================================


@pytest.fixture
def mock_settings() -> Settings:
    """Create test settings with mock values."""
    with patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "test_token_123",
            "TELEGRAM_ALLOWED_CHAT_IDS": "123456,789012",
            "TELEGRAM_ADMIN_CHAT_IDS": "123456",
            "OPENWEATHER_API_KEY": "test_api_key",
            "LOCATION_LATITUDE": "52.52",
            "LOCATION_LONGITUDE": "13.405",
            "DATABASE_PATH": ":memory:",
        },
    ):
        return Settings()


# ============================================================================
# Mock Database
# ============================================================================


@pytest.fixture
def mock_database() -> AsyncMock:
    """Create mock database."""
    db = AsyncMock()
    db.initialize = AsyncMock()
    db.close = AsyncMock()
    db.log_sensor_reading = AsyncMock()
    db.log_pump_event = AsyncMock()
    db.log_alert = AsyncMock()
    db.get_sensor_readings = AsyncMock(return_value=[])
    db.rotate_data = AsyncMock(return_value=0)
    return db


# ============================================================================
# Mock Weather Service
# ============================================================================


@pytest.fixture
def mock_weather_response() -> dict:
    """Create mock weather API response."""
    return {
        "weather": [{"main": "Clear", "description": "clear sky"}],
        "main": {"temp": 20.5, "humidity": 65},
        "wind": {"speed": 3.5},
        "clouds": {"all": 10},
        "rain": {},
    }


@pytest.fixture
def mock_weather_service() -> AsyncMock:
    """Create mock weather service."""
    from gartenroboter.services.weather import WeatherData

    service = AsyncMock()
    service.get_weather = AsyncMock(
        return_value=WeatherData(
            temperature=20.5,
            humidity=65,
            description="clear sky",
            wind_speed=3.5,
            clouds=10,
            rain_probability=None,
            rain_mm=None,
        )
    )
    return service


# ============================================================================
# Mock Sun Tracker
# ============================================================================


@pytest.fixture
def mock_sun_tracker() -> AsyncMock:
    """Create mock sun tracker."""
    service = AsyncMock()
    service.get_sunset_time = AsyncMock(
        return_value=datetime.now().replace(hour=20, minute=0)
    )
    service.get_sunrise_time = AsyncMock(
        return_value=datetime.now().replace(hour=6, minute=0)
    )
    service.is_after_sunset = AsyncMock(return_value=True)
    return service


# ============================================================================
# Mock Telegram
# ============================================================================


@pytest.fixture
def mock_telegram_bot() -> MagicMock:
    """Create mock Telegram bot."""
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def mock_notifier() -> AsyncMock:
    """Create mock notifier."""
    notifier = AsyncMock()
    notifier.start = AsyncMock()
    notifier.stop = AsyncMock()
    notifier.send = AsyncMock()
    notifier.send_immediate = AsyncMock(return_value=True)
    notifier.alerts_enabled = True
    return notifier


# ============================================================================
# Test Data Fixtures
# ============================================================================


@pytest.fixture
def soil_readings() -> list[int]:
    """Sample soil moisture readings (raw ADC values)."""
    return [300, 450, 600, 800]  # Varying moisture levels


@pytest.fixture
def dry_soil_readings() -> list[int]:
    """Dry soil readings (high values = dry)."""
    return [850, 900, 875, 920]


@pytest.fixture
def wet_soil_readings() -> list[int]:
    """Wet soil readings (low values = wet)."""
    return [200, 180, 220, 190]


@pytest.fixture
def water_level_full() -> float:
    """Water level when barrel is full (distance in cm)."""
    return 10.0


@pytest.fixture
def water_level_empty() -> float:
    """Water level when barrel is empty (distance in cm)."""
    return 100.0


@pytest.fixture
def water_level_low() -> float:
    """Water level when barrel is low (distance in cm)."""
    return 85.0


# ============================================================================
# Temporary Files
# ============================================================================


@pytest.fixture
def temp_config_file(tmp_path: Path) -> Path:
    """Create temporary config file path."""
    return tmp_path / "config.json"


@pytest.fixture
def temp_database_file(tmp_path: Path) -> Path:
    """Create temporary database file path."""
    return tmp_path / "test.db"


# ============================================================================
# Integration Test Helpers
# ============================================================================


@pytest.fixture
async def initialized_database(temp_database_file: Path) -> AsyncGenerator:
    """Create initialized database for integration tests."""
    from gartenroboter.infra.database import Database

    db = Database(temp_database_file)
    await db.initialize()

    yield db

    await db.close()


# ============================================================================
# Markers
# ============================================================================


def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line(
        "markers", "hardware: marks tests that require real hardware"
    )
