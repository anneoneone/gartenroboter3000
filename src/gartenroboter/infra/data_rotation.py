"""Data rotation for cleaning up old database records."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gartenroboter.infra.database import Database

logger = logging.getLogger(__name__)


class DataRotation:
    """Handles cleanup of old database records."""

    def __init__(
        self,
        database: Database,
        retention_days: int = 90,
    ) -> None:
        self.db = database
        self.retention_days = retention_days
        self._last_run: datetime | None = None

    def _get_cutoff_date(self) -> str:
        """Get the cutoff date for deletion."""
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        return cutoff.isoformat()

    async def rotate_sensor_readings(self) -> int:
        """Delete old sensor readings."""
        conn = await self.db._ensure_connected()
        cutoff = self._get_cutoff_date()

        cursor = await conn.execute(
            "DELETE FROM sensor_readings WHERE timestamp < ?",
            (cutoff,),
        )
        await conn.commit()

        deleted = cursor.rowcount
        if deleted > 0:
            logger.info("Deleted %d old sensor readings", deleted)
        return deleted

    async def rotate_pump_events(self) -> int:
        """Delete old pump events."""
        conn = await self.db._ensure_connected()
        cutoff = self._get_cutoff_date()

        cursor = await conn.execute(
            "DELETE FROM pump_events WHERE timestamp < ?",
            (cutoff,),
        )
        await conn.commit()

        deleted = cursor.rowcount
        if deleted > 0:
            logger.info("Deleted %d old pump events", deleted)
        return deleted

    async def rotate_watering_decisions(self) -> int:
        """Delete old watering decisions."""
        conn = await self.db._ensure_connected()
        cutoff = self._get_cutoff_date()

        cursor = await conn.execute(
            "DELETE FROM watering_decisions WHERE timestamp < ?",
            (cutoff,),
        )
        await conn.commit()

        deleted = cursor.rowcount
        if deleted > 0:
            logger.info("Deleted %d old watering decisions", deleted)
        return deleted

    async def rotate_weather_data(self) -> int:
        """Delete old weather data."""
        conn = await self.db._ensure_connected()
        cutoff = self._get_cutoff_date()

        cursor = await conn.execute(
            "DELETE FROM weather_data WHERE timestamp < ?",
            (cutoff,),
        )
        await conn.commit()

        deleted = cursor.rowcount
        if deleted > 0:
            logger.info("Deleted %d old weather records", deleted)
        return deleted

    async def rotate_config_changes(self) -> int:
        """Delete old config change logs."""
        conn = await self.db._ensure_connected()
        cutoff = self._get_cutoff_date()

        cursor = await conn.execute(
            "DELETE FROM config_changes WHERE timestamp < ?",
            (cutoff,),
        )
        await conn.commit()

        deleted = cursor.rowcount
        if deleted > 0:
            logger.info("Deleted %d old config changes", deleted)
        return deleted

    async def rotate_alerts(self) -> int:
        """Delete old alerts."""
        conn = await self.db._ensure_connected()
        cutoff = self._get_cutoff_date()

        cursor = await conn.execute(
            "DELETE FROM alerts WHERE timestamp < ?",
            (cutoff,),
        )
        await conn.commit()

        deleted = cursor.rowcount
        if deleted > 0:
            logger.info("Deleted %d old alerts", deleted)
        return deleted

    async def vacuum_database(self) -> None:
        """Reclaim disk space after deletions."""
        conn = await self.db._ensure_connected()
        await conn.execute("VACUUM")
        logger.info("Database vacuumed")

    async def run_rotation(self, vacuum: bool = True) -> dict[str, int]:
        """
        Run full data rotation.

        Args:
            vacuum: Whether to vacuum database after deletion

        Returns:
            Dictionary with count of deleted records per table
        """
        logger.info(
            "Starting data rotation (retention: %d days)",
            self.retention_days,
        )

        results = {
            "sensor_readings": await self.rotate_sensor_readings(),
            "pump_events": await self.rotate_pump_events(),
            "watering_decisions": await self.rotate_watering_decisions(),
            "weather_data": await self.rotate_weather_data(),
            "config_changes": await self.rotate_config_changes(),
            "alerts": await self.rotate_alerts(),
        }

        total_deleted = sum(results.values())

        if vacuum and total_deleted > 0:
            await self.vacuum_database()

        self._last_run = datetime.now(UTC)

        logger.info(
            "Data rotation complete: %d total records deleted",
            total_deleted,
        )

        return results

    def should_run(self) -> bool:
        """Check if rotation should run (once per day)."""
        if self._last_run is None:
            return True

        # Run once per day
        elapsed = datetime.now(UTC) - self._last_run
        return elapsed.total_seconds() >= 86400  # 24 hours
