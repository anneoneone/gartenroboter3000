"""Configuration manager for runtime config persistence."""

import json
import logging
from pathlib import Path
from typing import Any

from gartenroboter.config.settings import Settings

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manage runtime configuration persistence.

    Handles loading and saving configuration to JSON file,
    with support for runtime updates via Telegram bot.
    """

    def __init__(self, config_path: Path):
        """Initialize config manager.

        Args:
            config_path: Path to config.json file
        """
        self.config_path = config_path
        self._settings: Settings | None = None
        self._runtime_config: dict[str, Any] = {}

    @property
    def settings(self) -> Settings:
        """Get current settings."""
        if self._settings is None:
            raise RuntimeError("Settings not loaded. Call load() first.")
        return self._settings

    async def load(self) -> Settings:
        """Load settings from environment and config file.

        Returns:
            Loaded Settings instance
        """
        # Load runtime config from JSON if exists
        if self.config_path.exists():
            try:
                self._runtime_config = json.loads(self.config_path.read_text())
                logger.info(f"Loaded runtime config from {self.config_path}")
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in config file: {e}")
                self._runtime_config = {}
        else:
            self._runtime_config = {}

        # Create settings (loads from environment/.env)
        self._settings = Settings()

        # Apply runtime overrides
        self._apply_runtime_overrides()

        return self._settings

    async def save(self) -> None:
        """Save current runtime config to JSON file."""
        # Update runtime config from settings
        self._update_runtime_config()

        # Write to file
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        self.config_path.write_text(
            json.dumps(self._runtime_config, indent=2, default=str)
        )

        logger.info(f"Saved runtime config to {self.config_path}")

    def get_value(self, key: str) -> Any:
        """Get a configuration value by key.

        Args:
            key: Configuration key (e.g., 'pump_max_runtime')

        Returns:
            Current value for the key
        """
        settings = self.settings

        # Map keys to settings values
        key_map = {
            "pump_max_runtime": settings.pump.max_runtime,
            "pump_cooldown": settings.pump.cooldown,
            "soil_threshold_dry": settings.sensor.soil_threshold_dry,
            "water_level_min": settings.sensor.water_level_min,
            "pi_temp_warning": settings.system.pi_temp_warning,
            "pi_temp_critical": settings.system.pi_temp_critical,
        }

        return key_map.get(key)

    async def set_value(self, key: str, value: Any) -> None:
        """Set a configuration value by key.

        Args:
            key: Configuration key
            value: New value (already validated)
        """
        settings = self.settings

        # Apply to settings
        if key == "pump_max_runtime":
            settings.pump.max_runtime = int(value)
        elif key == "pump_cooldown":
            settings.pump.cooldown = int(value)
        elif key == "soil_threshold_dry":
            settings.sensor.soil_threshold_dry = int(value)
        elif key == "water_level_min":
            settings.sensor.water_level_min = int(value)
        elif key == "pi_temp_warning":
            settings.system.pi_temp_warning = int(value)
        elif key == "pi_temp_critical":
            settings.system.pi_temp_critical = int(value)
        else:
            raise ValueError(f"Unknown configuration key: {key}")

        # Save to file
        await self.save()

        logger.info(f"Configuration updated: {key} = {value}")

    async def set_soil_calibration(
        self,
        zone: int,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> None:
        """Set soil sensor calibration values.

        Args:
            zone: Zone index (1-4)
            min_value: Min raw ADC value (dry)
            max_value: Max raw ADC value (wet)
        """
        zone_key = f"zone_{zone}"
        if zone_key not in self.settings.sensor.calibration:
            raise ValueError(f"Invalid zone: {zone}")

        if min_value is not None:
            self.settings.sensor.calibration[zone_key]["min"] = min_value
        if max_value is not None:
            self.settings.sensor.calibration[zone_key]["max"] = max_value

        await self.save()
        logger.info(f"Soil sensor zone {zone} calibration updated")

    async def set_water_level_calibration(
        self,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> None:
        """Set water level sensor calibration values.

        Args:
            min_value: Min raw ADC value (empty)
            max_value: Max raw ADC value (full)
        """
        if min_value is not None:
            self.settings.sensor.calibration["water_level"]["min"] = min_value
        if max_value is not None:
            self.settings.sensor.calibration["water_level"]["max"] = max_value

        await self.save()
        logger.info("Water level sensor calibration updated")

    def _apply_runtime_overrides(self) -> None:
        """Apply runtime config overrides to settings."""
        if not self._runtime_config:
            return

        settings = self._settings

        # Pump settings
        if "pump" in self._runtime_config:
            pump_config = self._runtime_config["pump"]
            if "max_runtime" in pump_config:
                settings.pump.max_runtime = pump_config["max_runtime"]
            if "cooldown" in pump_config:
                settings.pump.cooldown = pump_config["cooldown"]

        # Sensor settings
        if "sensor" in self._runtime_config:
            sensor_config = self._runtime_config["sensor"]
            if "soil_threshold_dry" in sensor_config:
                settings.sensor.soil_threshold_dry = sensor_config["soil_threshold_dry"]
            if "water_level_min" in sensor_config:
                settings.sensor.water_level_min = sensor_config["water_level_min"]
            if "calibration" in sensor_config:
                settings.sensor.calibration = sensor_config["calibration"]

        # System settings
        if "system" in self._runtime_config:
            sys_config = self._runtime_config["system"]
            if "pi_temp_warning" in sys_config:
                settings.system.pi_temp_warning = sys_config["pi_temp_warning"]
            if "pi_temp_critical" in sys_config:
                settings.system.pi_temp_critical = sys_config["pi_temp_critical"]

        # Telegram whitelist
        if "telegram" in self._runtime_config:
            tg_config = self._runtime_config["telegram"]
            if "allowed_chat_ids" in tg_config:
                settings.telegram.allowed_chat_ids = list(tg_config["allowed_chat_ids"])
            if "admin_chat_ids" in tg_config:
                settings.telegram.admin_chat_ids = list(tg_config["admin_chat_ids"])

    def _update_runtime_config(self) -> None:
        """Update runtime config dict from current settings."""
        settings = self._settings

        self._runtime_config = {
            "pump": {
                "max_runtime": settings.pump.max_runtime,
                "cooldown": settings.pump.cooldown,
            },
            "sensor": {
                "soil_threshold_dry": settings.sensor.soil_threshold_dry,
                "water_level_min": settings.sensor.water_level_min,
                "calibration": settings.sensor.calibration,
            },
            "system": {
                "pi_temp_warning": settings.system.pi_temp_warning,
                "pi_temp_critical": settings.system.pi_temp_critical,
            },
            "telegram": {
                "allowed_chat_ids": list(settings.telegram.allowed_chat_ids),
                "admin_chat_ids": list(settings.telegram.admin_chat_ids),
            },
        }
