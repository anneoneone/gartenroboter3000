"""Configuration validation for Telegram bot commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar


class ValidationError(Exception):
    """Raised when configuration validation fails."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass
class ValidationResult:
    """Result of a configuration validation."""

    valid: bool
    value: Any = None
    error: str | None = None

class ConfigValidator:
    """Validates configuration values for Telegram bot updates."""

    # Define valid ranges and types for each setting
    VALIDATION_RULES: ClassVar[dict[str, dict[str, Any]]] = {
        "pump.max_runtime": {
            "type": int,
            "min": 10,
            "max": 300,
            "unit": "seconds",
            "description": "Maximum pump runtime per cycle",
        },
        "pump.cooldown": {
            "type": int,
            "min": 60,
            "max": 600,
            "unit": "seconds",
            "description": "Cooldown between pump cycles",
        },
        "sensor.soil_threshold_dry": {
            "type": int,
            "min": 0,
            "max": 100,
            "unit": "%",
            "description": "Soil moisture threshold (below = dry)",
        },
        "sensor.water_level_min": {
            "type": int,
            "min": 0,
            "max": 100,
            "unit": "%",
            "description": "Minimum water level for warnings",
        },
        "sensor.pi_temp_warning": {
            "type": int,
            "min": 50,
            "max": 85,
            "unit": "°C",
            "description": "Pi temperature warning threshold",
        },
        "scheduler.sensor_interval": {
            "type": int,
            "min": 5,
            "max": 300,
            "unit": "seconds",
            "description": "Sensor polling interval",
        },
        "scheduler.watering_interval": {
            "type": int,
            "min": 60,
            "max": 3600,
            "unit": "seconds",
            "description": "Watering check interval",
        },
    }

    @classmethod
    def get_configurable_keys(cls) -> list[str]:
        """Get list of all configurable setting keys."""
        return list(cls.VALIDATION_RULES.keys())

    @classmethod
    def get_setting_info(cls, key: str) -> dict[str, Any] | None:
        """Get validation info for a setting key."""
        return cls.VALIDATION_RULES.get(key)

    @classmethod
    def validate(cls, key: str, value: str) -> ValidationResult:
        """
        Validate a configuration value.

        Args:
            key: Setting key (e.g., "pump.max_runtime")
            value: String value to validate and convert

        Returns:
            ValidationResult with converted value or error message
        """
        if key not in cls.VALIDATION_RULES:
            return ValidationResult(
                valid=False,
                error=f"Unknown setting: {key}\n\nValid settings:\n"
                + "\n".join(f"  • {k}" for k in cls.VALIDATION_RULES),
            )

        rules = cls.VALIDATION_RULES[key]

        # Try to convert to the expected type
        try:
            if rules["type"] is int:
                converted_value = int(value)
            elif rules["type"] is float:
                converted_value = float(value)
            elif rules["type"] is bool:
                converted_value = value.lower() in ("true", "1", "yes", "on")
            else:
                converted_value = value
        except ValueError:
            type_name = rules["type"].__name__
            return ValidationResult(
                valid=False,
                error=f"Invalid value: '{value}' is not a valid {type_name}",
            )

        # Check range constraints
        if "min" in rules and converted_value < rules["min"]:
            min_val = rules["min"]
            unit = rules["unit"]
            return ValidationResult(
                valid=False,
                error=f"Value {converted_value} is below minimum ({min_val} {unit})",
            )

        if "max" in rules and converted_value > rules["max"]:
            max_val = rules["max"]
            unit = rules["unit"]
            return ValidationResult(
                valid=False,
                error=f"Value {converted_value} is above maximum ({max_val} {unit})",
            )

        return ValidationResult(valid=True, value=converted_value)

    @classmethod
    def validate_setting(cls, key: str, value: str) -> Any:
        """
        Validate and return a configuration value, raising on error.

        Args:
            key: Setting key (e.g., "pump.max_runtime")
            value: String value to validate and convert

        Returns:
            The converted/validated value

        Raises:
            ValidationError: If validation fails
        """
        result = cls.validate(key, value)
        if not result.valid:
            raise ValidationError(result.error or "Validation failed")
        return result.value

    @classmethod
    def format_help(cls) -> str:
        """Format help text for all configurable settings."""
        lines = ["📋 *Configurable Settings*\n"]

        for key, rules in cls.VALIDATION_RULES.items():
            unit = rules.get("unit", "")
            min_val = rules.get("min", "")
            max_val = rules.get("max", "")
            description = rules.get("description", "")

            lines.append(f"• `{key}`")
            lines.append(f"  {description}")
            if min_val != "" and max_val != "":
                lines.append(f"  Range: {min_val}-{max_val} {unit}")
            lines.append("")

        lines.append("\n💡 *Usage:* `/set <key> <value>`")
        lines.append("Example: `/set pump.max_runtime 120`")

        return "\n".join(lines)
