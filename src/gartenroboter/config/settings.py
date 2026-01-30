"""Pydantic settings for Gartenroboter configuration."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class TelegramSettings(BaseSettings):
    """Telegram bot configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TELEGRAM_",
        extra="ignore",
    )

    bot_token: str = Field(default="", description="Telegram bot token from @BotFather")
    allowed_chat_ids: list[int] = Field(
        default_factory=list,
        description="Comma-separated list of allowed chat IDs",
    )
    admin_chat_ids: list[int] = Field(
        default_factory=list,
        description="Comma-separated list of admin chat IDs",
    )

    @field_validator("allowed_chat_ids", "admin_chat_ids", mode="before")
    @classmethod
    def parse_chat_ids(cls, v: Any) -> list[int]:
        """Parse comma-separated chat IDs from env."""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [int(x) for x in v]
        return []


class WeatherSettings(BaseSettings):
    """Weather API configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="OPENWEATHER_",
        extra="ignore",
    )

    api_key: str = Field(default="", description="OpenWeather API key")
    cache_ttl_seconds: int = Field(default=600, description="Cache TTL in seconds")


class LocationSettings(BaseSettings):
    """Location configuration for sunset calculation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="LOCATION_",
        extra="ignore",
    )

    latitude: float = Field(default=52.52, description="Latitude")
    longitude: float = Field(default=13.405, description="Longitude")
    timezone: str = Field(default="Europe/Berlin", description="Timezone")


class SensorSettings(BaseSettings):
    """Sensor threshold configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SENSOR_",
        extra="ignore",
    )

    soil_threshold_dry: int = Field(
        default=30,
        ge=0,
        le=100,
        description="Soil moisture threshold (0-100%, below = dry)",
    )
    water_level_min: int = Field(
        default=15,
        ge=0,
        le=100,
        description="Minimum water level (0-100%, below = warning)",
    )
    pi_temp_warning: int = Field(
        default=70,
        ge=50,
        le=85,
        description="Pi temperature warning threshold (Celsius)",
    )
    # Calibration values per sensor (min/max raw ADC values)
    calibration: dict[str, dict[str, int]] = Field(
        default_factory=lambda: {
            "zone_1": {"min": 300, "max": 700},
            "zone_2": {"min": 300, "max": 700},
            "zone_3": {"min": 300, "max": 700},
            "zone_4": {"min": 300, "max": 700},
            "water_level": {"min": 0, "max": 1023},
        },
        description="Calibration values per sensor",
    )


class PumpSettings(BaseSettings):
    """Pump control configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PUMP_",
        extra="ignore",
    )

    max_runtime: int = Field(
        default=180,
        ge=10,
        le=300,
        description="Maximum pump runtime per cycle (seconds)",
    )
    cooldown: int = Field(
        default=300,
        ge=60,
        le=600,
        description="Cooldown between pump cycles (seconds)",
    )


class GpioSettings(BaseSettings):
    """GPIO pin configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="GPIO_",
        extra="ignore",
    )

    adc_cs_pin: int = Field(default=8, description="MCP3008 chip select pin")
    soil_sensor_channels: list[int] = Field(
        default_factory=lambda: [0, 1, 2, 3],
        description="MCP3008 channels for soil sensors",
    )
    water_level_channel: int = Field(
        default=4,
        description="MCP3008 channel for water level",
    )
    pump_relay_pin: int = Field(default=17, description="Pump relay GPIO pin")
    ultrasonic_trigger_pin: int = Field(
        default=23,
        description="HC-SR04 trigger pin",
    )
    ultrasonic_echo_pin: int = Field(default=24, description="HC-SR04 echo pin")

    @field_validator("soil_sensor_channels", mode="before")
    @classmethod
    def parse_channels(cls, v: Any) -> list[int]:
        """Parse comma-separated channels from env."""
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [int(x) for x in v]
        return [0, 1, 2, 3]


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="DATABASE_",
        extra="ignore",
    )

    path: Path = Field(
        default=Path("data/gartenroboter.db"),
        description="Database file path",
    )
    retention_days: int = Field(
        default=90,
        ge=1,
        le=365,
        description="Data retention period in days",
    )


class SchedulerSettings(BaseSettings):
    """Scheduler configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCHEDULER_",
        extra="ignore",
    )

    sensor_interval: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Sensor polling interval (seconds)",
    )
    watering_interval: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Watering check interval (seconds)",
    )


class SystemSettings(BaseSettings):
    """System monitoring configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SYSTEM_",
        extra="ignore",
    )

    pi_temp_warning: int = Field(
        default=70,
        ge=50,
        le=85,
        description="Pi temperature warning threshold (Celsius)",
    )
    pi_temp_critical: int = Field(
        default=80,
        ge=60,
        le=90,
        description="Pi temperature critical threshold (Celsius)",
    )


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )

    # Nested settings
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    weather: WeatherSettings = Field(default_factory=WeatherSettings)
    location: LocationSettings = Field(default_factory=LocationSettings)
    sensor: SensorSettings = Field(default_factory=SensorSettings)
    pump: PumpSettings = Field(default_factory=PumpSettings)
    gpio: GpioSettings = Field(default_factory=GpioSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    system: SystemSettings = Field(default_factory=SystemSettings)

    # Runtime settings
    mock_mode: bool = Field(
        default=False,
        description="Use mock GPIO/sensors for development",
    )
    log_level: str = Field(default="INFO", description="Logging level")

    # Runtime config file (for Telegram-editable settings)
    runtime_config_path: Path = Field(
        default=Path("runtime_config.json"),
        description="Path to runtime config file",
    )

    def model_post_init(self, __context: Any) -> None:
        """Load runtime config overrides after initialization."""
        self._load_runtime_config()

    def _load_runtime_config(self) -> None:
        """Load runtime configuration overrides from JSON file."""
        if not self.runtime_config_path.exists():
            return

        try:
            runtime_config = json.loads(self.runtime_config_path.read_text())

            # Apply overrides to mutable settings
            if "sensor" in runtime_config:
                for key, value in runtime_config["sensor"].items():
                    if hasattr(self.sensor, key):
                        setattr(self.sensor, key, value)

            if "pump" in runtime_config:
                for key, value in runtime_config["pump"].items():
                    if hasattr(self.pump, key):
                        setattr(self.pump, key, value)

            if (
                "telegram" in runtime_config
                and "allowed_chat_ids" in runtime_config["telegram"]
            ):
                self.telegram.allowed_chat_ids = runtime_config["telegram"][
                    "allowed_chat_ids"
                ]

            logger.info("Loaded runtime config from %s", self.runtime_config_path)
        except Exception as e:
            logger.warning("Failed to load runtime config: %s", e)

    def save_runtime_config(self) -> None:
        """Save current runtime configuration to JSON file."""
        runtime_config = {
            "sensor": {
                "soil_threshold_dry": self.sensor.soil_threshold_dry,
                "water_level_min": self.sensor.water_level_min,
                "pi_temp_warning": self.sensor.pi_temp_warning,
                "calibration": self.sensor.calibration,
            },
            "pump": {
                "max_runtime": self.pump.max_runtime,
                "cooldown": self.pump.cooldown,
            },
            "telegram": {
                "allowed_chat_ids": self.telegram.allowed_chat_ids,
            },
        }

        # Ensure parent directory exists
        self.runtime_config_path.parent.mkdir(parents=True, exist_ok=True)

        self.runtime_config_path.write_text(json.dumps(runtime_config, indent=2))

        logger.info("Saved runtime config to %s", self.runtime_config_path)

    def update_setting(self, key: str, value: Any) -> bool:
        """
        Update a setting by dot-notation key.

        Args:
            key: Setting key (e.g., "pump.max_runtime", "sensor.soil_threshold_dry")
            value: New value

        Returns:
            True if update was successful, False otherwise
        """
        parts = key.split(".")
        if len(parts) != 2:
            return False

        section, setting = parts

        # Map section names to settings objects
        section_map = {
            "sensor": self.sensor,
            "pump": self.pump,
            "telegram": self.telegram,
        }

        if section not in section_map:
            return False

        section_obj = section_map[section]
        if not hasattr(section_obj, setting):
            return False

        try:
            # Validate and set the value
            setattr(section_obj, setting, value)
            self.save_runtime_config()
            return True
        except Exception as e:
            logger.error("Failed to update setting %s: %s", key, e)
            return False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def reload_settings() -> Settings:
    """Reload settings (clear cache and reload)."""
    get_settings.cache_clear()
    return get_settings()
