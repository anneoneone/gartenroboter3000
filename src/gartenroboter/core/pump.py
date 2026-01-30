"""Pump controller with state machine, timeout, and cooldown."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gartenroboter.config.settings import GpioSettings, PumpSettings
    from gartenroboter.infra.gpio import GpioInterface

logger = logging.getLogger(__name__)


class PumpState(Enum):
    """Pump operational states."""

    IDLE = "idle"
    RUNNING = "running"
    COOLDOWN = "cooldown"
    ERROR = "error"


@dataclass
class PumpStatus:
    """Current pump status."""

    state: PumpState
    is_running: bool
    runtime_seconds: float
    cooldown_remaining_seconds: float
    last_start: datetime | None
    last_stop: datetime | None
    total_runtime_today: float
    error_message: str | None = None


@dataclass
class PumpEvent:
    """Pump operation event for logging."""

    event_type: str  # "start", "stop", "error", "cooldown_start", "cooldown_end"
    zone_id: int | None
    duration_seconds: float | None
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class PumpController:
    """Controls the water pump with safety features."""

    def __init__(
        self,
        gpio: GpioInterface,
        settings: PumpSettings,
        gpio_settings: GpioSettings,
    ) -> None:
        self.gpio = gpio
        self.settings = settings
        self.gpio_settings = gpio_settings

        self._state = PumpState.IDLE
        self._current_zone: int | None = None
        self._start_time: datetime | None = None
        self._last_stop_time: datetime | None = None
        self._total_runtime_today: float = 0.0
        self._last_reset_date = datetime.now(UTC).date()
        self._error_message: str | None = None
        self._running_task: asyncio.Task[None] | None = None
        self._cooldown_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    def _reset_daily_counter(self) -> None:
        """Reset daily runtime counter if new day."""
        today = datetime.now(UTC).date()
        if today != self._last_reset_date:
            self._total_runtime_today = 0.0
            self._last_reset_date = today  # type: ignore[assignment]
            logger.info("Daily runtime counter reset")

    def _get_cooldown_remaining(self) -> float:
        """Get remaining cooldown time in seconds."""
        if self._last_stop_time is None:
            return 0.0

        elapsed = (datetime.now(UTC) - self._last_stop_time).total_seconds()
        remaining = self.settings.cooldown - elapsed
        return max(0.0, remaining)

    def _get_runtime(self) -> float:
        """Get current runtime in seconds."""
        if self._start_time is None:
            return 0.0
        return (datetime.now(UTC) - self._start_time).total_seconds()

    @property
    def state(self) -> PumpState:
        """Get current pump state (sync property for quick access)."""
        return self._state

    @property
    def is_in_cooldown(self) -> bool:
        """Check if pump is in cooldown (sync property)."""
        return self._state == PumpState.COOLDOWN

    @property
    def cooldown_remaining(self) -> float:
        """Get remaining cooldown time in seconds (sync property)."""
        return self._get_cooldown_remaining()

    async def get_status(self) -> PumpStatus:
        """Get current pump status."""
        async with self._lock:
            self._reset_daily_counter()

            return PumpStatus(
                state=self._state,
                is_running=self._state == PumpState.RUNNING,
                runtime_seconds=self._get_runtime(),
                cooldown_remaining_seconds=self._get_cooldown_remaining(),
                last_start=self._start_time,
                last_stop=self._last_stop_time,
                total_runtime_today=self._total_runtime_today,
                error_message=self._error_message,
            )

    async def can_start(self) -> tuple[bool, str]:
        """Check if pump can be started."""
        async with self._lock:
            self._reset_daily_counter()

            if self._state == PumpState.RUNNING:
                return False, "Pump is already running"

            if self._state == PumpState.ERROR:
                return False, f"Pump in error state: {self._error_message}"

            cooldown = self._get_cooldown_remaining()
            if cooldown > 0:
                return False, f"Pump in cooldown: {cooldown:.0f}s remaining"

            return True, "Ready"

    async def start(
        self,
        zone_id: int,
        duration_seconds: float | None = None,
        reason: str = "manual",
    ) -> PumpEvent:
        """
        Start the pump for a zone.

        Args:
            zone_id: Zone being watered
            duration_seconds: Max duration (defaults to settings.max_runtime)
            reason: Reason for starting (for logging)

        Returns:
            PumpEvent with start details
        """
        can_start, message = await self.can_start()
        if not can_start:
            logger.warning("Cannot start pump: %s", message)
            return PumpEvent(
                event_type="error",
                zone_id=zone_id,
                duration_seconds=None,
                reason=message,
            )

        max_duration = duration_seconds or self.settings.max_runtime
        # Enforce absolute maximum
        max_duration = min(max_duration, self.settings.max_runtime)

        async with self._lock:
            try:
                await self.gpio.set_relay(self.gpio_settings.pump_relay_pin, True)
                self._state = PumpState.RUNNING
                self._current_zone = zone_id
                self._start_time = datetime.now(UTC)
                self._error_message = None

                logger.info(
                    "Pump started for zone %d, max duration: %.0fs, reason: %s",
                    zone_id,
                    max_duration,
                    reason,
                )

            except Exception as e:
                self._state = PumpState.ERROR
                self._error_message = str(e)
                logger.exception("Failed to start pump")
                return PumpEvent(
                    event_type="error",
                    zone_id=zone_id,
                    duration_seconds=None,
                    reason=f"Start failed: {e}",
                )

        # Schedule automatic stop after max duration
        self._running_task = asyncio.create_task(self._auto_stop(max_duration, zone_id))

        return PumpEvent(
            event_type="start",
            zone_id=zone_id,
            duration_seconds=max_duration,
            reason=reason,
        )

    async def _auto_stop(self, duration: float, zone_id: int) -> None:
        """Automatically stop pump after duration."""
        try:
            await asyncio.sleep(duration)
            await self.stop(reason="max_runtime_reached")
        except asyncio.CancelledError:
            logger.debug("Auto-stop task cancelled for zone %d", zone_id)

    async def stop(self, reason: str = "manual") -> PumpEvent:
        """Stop the pump."""
        async with self._lock:
            if self._state != PumpState.RUNNING:
                return PumpEvent(
                    event_type="error",
                    zone_id=self._current_zone,
                    duration_seconds=None,
                    reason="Pump not running",
                )

            # Cancel auto-stop task if running
            if self._running_task and not self._running_task.done():
                self._running_task.cancel()
                self._running_task = None

            runtime = self._get_runtime()
            zone_id = self._current_zone

            try:
                await self.gpio.set_relay(self.gpio_settings.pump_relay_pin, False)

                self._total_runtime_today += runtime
                self._last_stop_time = datetime.now(UTC)
                self._state = PumpState.COOLDOWN
                self._start_time = None
                self._current_zone = None

                logger.info(
                    "Pump stopped for zone %s after %.1fs, reason: %s",
                    zone_id,
                    runtime,
                    reason,
                )

                # Schedule cooldown end
                self._cooldown_task = asyncio.create_task(self._end_cooldown())

            except Exception as e:
                self._state = PumpState.ERROR
                self._error_message = str(e)
                logger.exception("Failed to stop pump")
                return PumpEvent(
                    event_type="error",
                    zone_id=zone_id,
                    duration_seconds=runtime,
                    reason=f"Stop failed: {e}",
                )

        return PumpEvent(
            event_type="stop",
            zone_id=zone_id,
            duration_seconds=runtime,
            reason=reason,
        )

    async def _end_cooldown(self) -> None:
        """End cooldown period."""
        await asyncio.sleep(self.settings.cooldown)

        async with self._lock:
            if self._state == PumpState.COOLDOWN:
                self._state = PumpState.IDLE
                logger.info("Pump cooldown ended, ready for next cycle")

    async def emergency_stop(self) -> PumpEvent:
        """Emergency stop - force stop regardless of state."""
        async with self._lock:
            # Cancel any running tasks
            if self._running_task and not self._running_task.done():
                self._running_task.cancel()
                self._running_task = None

            runtime = self._get_runtime()
            zone_id = self._current_zone

            try:
                await self.gpio.set_relay(self.gpio_settings.pump_relay_pin, False)
            except Exception:
                logger.exception("Emergency stop GPIO failed")

            self._state = PumpState.IDLE
            self._start_time = None
            self._current_zone = None
            self._last_stop_time = datetime.now(UTC)

            logger.warning("Emergency stop executed")

        return PumpEvent(
            event_type="stop",
            zone_id=zone_id,
            duration_seconds=runtime,
            reason="emergency_stop",
        )

    async def cleanup(self) -> None:
        """Cleanup on shutdown."""
        if self._state == PumpState.RUNNING:
            await self.emergency_stop()
