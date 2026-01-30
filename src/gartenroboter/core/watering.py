"""Watering decision engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gartenroboter.config.settings import Settings
    from gartenroboter.core.pump import PumpController, PumpEvent
    from gartenroboter.core.sensors import (
        AllSensorReadings,
        SensorManager,
        SoilMoistureReading,
    )
    from gartenroboter.services.sun import SunTracker
    from gartenroboter.services.weather import WeatherService

logger = logging.getLogger(__name__)


class WateringDecision(Enum):
    """Result of watering decision."""

    WATER = "water"
    SKIP_NOT_DRY = "skip_not_dry"
    SKIP_BEFORE_SUNSET = "skip_before_sunset"
    SKIP_LOW_WATER = "skip_low_water"
    SKIP_PI_TOO_HOT = "skip_pi_too_hot"
    SKIP_PUMP_UNAVAILABLE = "skip_pump_unavailable"
    SKIP_RAIN_EXPECTED = "skip_rain_expected"
    ERROR = "error"


@dataclass
class WateringResult:
    """Result of a watering check."""

    zone_id: int
    decision: WateringDecision
    reason: str
    soil_moisture_percent: float | None = None
    pump_event: PumpEvent | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class WateringCycleResult:
    """Result of a full watering cycle (all zones)."""

    results: list[WateringResult]
    zones_watered: int
    zones_skipped: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def any_watered(self) -> bool:
        """Check if any zone was watered."""
        return self.zones_watered > 0


class WateringEngine:
    """Decides when and where to water based on sensors and conditions."""

    def __init__(
        self,
        settings: Settings,
        sensor_manager: SensorManager,
        pump_controller: PumpController,
        sun_tracker: SunTracker,
        weather_service: WeatherService,
    ) -> None:
        self.settings = settings
        self.sensors = sensor_manager
        self.pump = pump_controller
        self.sun = sun_tracker
        self.weather = weather_service

    async def _check_preconditions(
        self,
        readings: AllSensorReadings,
    ) -> tuple[bool, WateringDecision, str]:
        """
        Check global preconditions for watering.

        Returns:
            (can_water, decision, reason)
        """
        # Check Pi temperature
        if readings.pi_temperature.is_warning:
            temp = readings.pi_temperature.temperature_celsius
            return (
                False,
                WateringDecision.SKIP_PI_TOO_HOT,
                f"Pi temperature too high: {temp:.1f}°C",
            )

        # Check water level
        if readings.water_level.is_low:
            return (
                False,
                WateringDecision.SKIP_LOW_WATER,
                f"Water level too low: {readings.water_level.level_percent:.1f}%",
            )

        # Check sunset
        is_after_sunset = await self.sun.is_after_sunset()
        if not is_after_sunset:
            sunset_time = await self.sun.get_sunset_time()
            sunset_str = sunset_time.strftime("%H:%M") if sunset_time else "unknown"
            return (
                False,
                WateringDecision.SKIP_BEFORE_SUNSET,
                f"Before sunset (sunset at {sunset_str})",
            )

        # Check rain forecast (optional - don't block if weather unavailable)
        try:
            rain_expected = await self.weather.is_rain_expected_today()
            if rain_expected:
                return (
                    False,
                    WateringDecision.SKIP_RAIN_EXPECTED,
                    "Rain expected in forecast",
                )
        except Exception as e:
            logger.warning("Weather check failed, continuing: %s", e)

        # Check pump availability
        can_start, pump_message = await self.pump.can_start()
        if not can_start:
            return (
                False,
                WateringDecision.SKIP_PUMP_UNAVAILABLE,
                f"Pump unavailable: {pump_message}",
            )

        return True, WateringDecision.WATER, "Preconditions met"

    async def check_zone(
        self,
        zone_id: int,
        soil_reading: SoilMoistureReading,
        readings: AllSensorReadings,
    ) -> WateringResult:
        """
        Check if a specific zone needs watering.

        Args:
            zone_id: Zone to check
            soil_reading: Soil moisture reading for this zone
            readings: All sensor readings for precondition checks

        Returns:
            WateringResult with decision
        """
        # Check if soil is dry
        if not soil_reading.is_dry:
            return WateringResult(
                zone_id=zone_id,
                decision=WateringDecision.SKIP_NOT_DRY,
                reason=f"Soil moisture OK: {soil_reading.moisture_percent:.1f}%",
                soil_moisture_percent=soil_reading.moisture_percent,
            )

        # Check global preconditions
        can_water, decision, reason = await self._check_preconditions(readings)
        if not can_water:
            return WateringResult(
                zone_id=zone_id,
                decision=decision,
                reason=reason,
                soil_moisture_percent=soil_reading.moisture_percent,
            )

        # All checks passed - water this zone
        moisture = soil_reading.moisture_percent
        threshold = self.settings.sensor.soil_threshold_dry
        return WateringResult(
            zone_id=zone_id,
            decision=WateringDecision.WATER,
            reason=f"Zone {zone_id} needs water: {moisture:.1f}% < {threshold}%",
            soil_moisture_percent=soil_reading.moisture_percent,
        )

    async def water_zone(
        self,
        zone_id: int,
        reason: str = "auto",
    ) -> WateringResult:
        """
        Water a specific zone.

        Args:
            zone_id: Zone to water
            reason: Reason for watering (for logging)

        Returns:
            WateringResult with pump event
        """
        pump_event = await self.pump.start(
            zone_id=zone_id,
            reason=reason,
        )

        if pump_event.event_type == "error":
            return WateringResult(
                zone_id=zone_id,
                decision=WateringDecision.ERROR,
                reason=pump_event.reason,
                pump_event=pump_event,
            )

        return WateringResult(
            zone_id=zone_id,
            decision=WateringDecision.WATER,
            reason=f"Watering zone {zone_id}",
            pump_event=pump_event,
        )

    async def run_cycle(self) -> WateringCycleResult:
        """
        Run a full watering cycle - check all zones and water if needed.

        Strategy: Water ANY zone that is dry (one at a time, with cooldown between).

        Returns:
            WateringCycleResult with all zone results
        """
        logger.info("Starting watering cycle")

        results: list[WateringResult] = []
        zones_watered = 0
        zones_skipped = 0

        try:
            # Read all sensors
            readings = await self.sensors.read_all()

            # Check each soil sensor
            for soil_reading in readings.soil_moisture:
                zone_id = soil_reading.zone_id

                # Check if zone needs watering
                result = await self.check_zone(zone_id, soil_reading, readings)

                if result.decision == WateringDecision.WATER:
                    # Water this zone
                    water_result = await self.water_zone(
                        zone_id=zone_id,
                        reason="auto_cycle",
                    )

                    if water_result.decision == WateringDecision.WATER:
                        zones_watered += 1
                        logger.info("Watered zone %d", zone_id)

                        # Wait for pump to finish (it auto-stops after max_runtime)
                        # The pump has cooldown, so next zone will wait if needed
                        await self._wait_for_pump()
                    else:
                        zones_skipped += 1
                        result = water_result

                    results.append(water_result)
                else:
                    zones_skipped += 1
                    results.append(result)
                    logger.debug("Zone %d skipped: %s", zone_id, result.reason)

        except Exception as e:
            logger.exception("Watering cycle error")
            results.append(
                WateringResult(
                    zone_id=-1,
                    decision=WateringDecision.ERROR,
                    reason=f"Cycle error: {e}",
                )
            )

        cycle_result = WateringCycleResult(
            results=results,
            zones_watered=zones_watered,
            zones_skipped=zones_skipped,
        )

        logger.info(
            "Watering cycle complete: %d watered, %d skipped",
            zones_watered,
            zones_skipped,
        )

        return cycle_result

    async def _wait_for_pump(self) -> None:
        """Wait for pump to finish running."""
        import asyncio

        while True:
            status = await self.pump.get_status()
            if not status.is_running:
                break
            await asyncio.sleep(1)

    async def manual_water(
        self,
        zone_id: int,
        duration_seconds: float | None = None,
        bypass_checks: bool = False,
    ) -> WateringResult:
        """
        Manually trigger watering for a zone.

        Args:
            zone_id: Zone to water
            duration_seconds: Override duration (uses settings default if None)
            bypass_checks: Skip precondition checks (emergency watering)

        Returns:
            WateringResult
        """
        logger.info(
            "Manual water request for zone %d (bypass=%s)",
            zone_id,
            bypass_checks,
        )

        if not bypass_checks:
            # Check preconditions
            readings = await self.sensors.read_all()
            can_water, decision, reason = await self._check_preconditions(readings)

            if not can_water:
                return WateringResult(
                    zone_id=zone_id,
                    decision=decision,
                    reason=f"Manual water blocked: {reason}",
                )

        # Start pump
        pump_event = await self.pump.start(
            zone_id=zone_id,
            duration_seconds=duration_seconds,
            reason="manual",
        )

        if pump_event.event_type == "error":
            return WateringResult(
                zone_id=zone_id,
                decision=WateringDecision.ERROR,
                reason=pump_event.reason,
                pump_event=pump_event,
            )

        return WateringResult(
            zone_id=zone_id,
            decision=WateringDecision.WATER,
            reason="Manual watering started",
            pump_event=pump_event,
        )
