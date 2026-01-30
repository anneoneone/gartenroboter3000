"""Unit tests for configuration validation."""

import pytest

from gartenroboter.config.validation import ConfigValidator, ValidationError


class TestConfigValidator:
    """Tests for ConfigValidator class."""

    def test_validate_pump_max_runtime_valid(self):
        """Test valid pump max runtime values."""
        assert ConfigValidator.validate_setting("pump_max_runtime", "60") == 60
        assert ConfigValidator.validate_setting("pump_max_runtime", "180") == 180
        assert ConfigValidator.validate_setting("pump_max_runtime", "10") == 10
        assert ConfigValidator.validate_setting("pump_max_runtime", "300") == 300

    def test_validate_pump_max_runtime_invalid_range(self):
        """Test invalid pump max runtime range."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_setting("pump_max_runtime", "5")
        assert "between 10 and 300" in str(exc_info.value)

        with pytest.raises(ValidationError):
            ConfigValidator.validate_setting("pump_max_runtime", "500")

    def test_validate_pump_max_runtime_invalid_type(self):
        """Test invalid pump max runtime type."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_setting("pump_max_runtime", "abc")
        assert "valid int" in str(exc_info.value)

    def test_validate_soil_threshold_valid(self):
        """Test valid soil threshold values."""
        assert ConfigValidator.validate_setting("soil_threshold_1", "30") == 30.0
        assert ConfigValidator.validate_setting("soil_threshold_2", "0") == 0.0
        assert ConfigValidator.validate_setting("soil_threshold_3", "100") == 100.0
        assert ConfigValidator.validate_setting("soil_threshold_4", "45.5") == 45.5

    def test_validate_soil_threshold_invalid_range(self):
        """Test invalid soil threshold range."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_setting("soil_threshold_1", "-10")

        with pytest.raises(ValidationError):
            ConfigValidator.validate_setting("soil_threshold_1", "150")

    def test_validate_pi_temp_warning_valid(self):
        """Test valid Pi temperature warning values."""
        assert ConfigValidator.validate_setting("pi_temp_warning", "65") == 65.0
        assert ConfigValidator.validate_setting("pi_temp_warning", "50") == 50.0
        assert ConfigValidator.validate_setting("pi_temp_warning", "85") == 85.0

    def test_validate_pi_temp_warning_invalid(self):
        """Test invalid Pi temperature warning values."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_setting("pi_temp_warning", "40")

        with pytest.raises(ValidationError):
            ConfigValidator.validate_setting("pi_temp_warning", "95")

    def test_validate_unknown_key(self):
        """Test validation of unknown key."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_setting("unknown_key", "123")
        assert "Unknown setting key" in str(exc_info.value)

    def test_validate_case_insensitive(self):
        """Test key validation is case-insensitive."""
        assert ConfigValidator.validate_setting("PUMP_MAX_RUNTIME", "60") == 60
        assert ConfigValidator.validate_setting("Pump_Max_Runtime", "60") == 60

    def test_validate_gpio_pin_valid(self):
        """Test valid GPIO pin numbers."""
        assert ConfigValidator.validate_gpio_pin(17) == 17
        assert ConfigValidator.validate_gpio_pin(2) == 2
        assert ConfigValidator.validate_gpio_pin(27) == 27

    def test_validate_gpio_pin_invalid(self):
        """Test invalid GPIO pin numbers."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_gpio_pin(0)

        with pytest.raises(ValidationError):
            ConfigValidator.validate_gpio_pin(1)

        with pytest.raises(ValidationError):
            ConfigValidator.validate_gpio_pin(28)

    def test_validate_coordinates_valid(self):
        """Test valid coordinates."""
        lat, lon = ConfigValidator.validate_coordinates(52.52, 13.405)
        assert lat == 52.52
        assert lon == 13.405

        # Edge cases
        ConfigValidator.validate_coordinates(-90, -180)
        ConfigValidator.validate_coordinates(90, 180)
        ConfigValidator.validate_coordinates(0, 0)

    def test_validate_coordinates_invalid_latitude(self):
        """Test invalid latitude."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_coordinates(-91, 0)
        assert "Latitude" in str(exc_info.value)

        with pytest.raises(ValidationError):
            ConfigValidator.validate_coordinates(91, 0)

    def test_validate_coordinates_invalid_longitude(self):
        """Test invalid longitude."""
        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_coordinates(0, -181)
        assert "Longitude" in str(exc_info.value)

        with pytest.raises(ValidationError):
            ConfigValidator.validate_coordinates(0, 181)

    def test_validate_chat_id(self):
        """Test chat ID validation."""
        assert ConfigValidator.validate_chat_id(123456) == 123456
        assert ConfigValidator.validate_chat_id("789012") == 789012
        assert ConfigValidator.validate_chat_id("-100123456") == -100123456

    def test_validate_chat_id_invalid(self):
        """Test invalid chat ID."""
        with pytest.raises(ValidationError):
            ConfigValidator.validate_chat_id("not_a_number")

    def test_validate_all_success(self):
        """Test validating multiple settings at once."""
        settings = {
            "pump_max_runtime": "120",
            "pump_cooldown": "180",
            "soil_threshold_1": "35",
        }

        validated = ConfigValidator.validate_all(settings)

        assert validated["pump_max_runtime"] == 120
        assert validated["pump_cooldown"] == 180
        assert validated["soil_threshold_1"] == 35.0

    def test_validate_all_with_errors(self):
        """Test validating multiple settings with errors."""
        settings = {
            "pump_max_runtime": "5",  # Too low
            "pump_cooldown": "1000",  # Too high
        }

        with pytest.raises(ValidationError) as exc_info:
            ConfigValidator.validate_all(settings)

        assert "Multiple validation errors" in str(exc_info.value)
