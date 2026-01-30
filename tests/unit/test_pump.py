"""Unit tests for pump controller."""

from gartenroboter.core.pump import PumpState


class TestPumpState:
    """Tests for PumpState enum."""

    def test_pump_states_exist(self):
        """Test that all pump states are defined."""
        assert PumpState.IDLE.value == "idle"
        assert PumpState.RUNNING.value == "running"
        assert PumpState.COOLDOWN.value == "cooldown"
        assert PumpState.ERROR.value == "error"

    def test_pump_state_values(self):
        """Test pump state values are strings."""
        for state in PumpState:
            assert isinstance(state.value, str)
