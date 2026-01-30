"""SQLite database layer with async support."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiosqlite

if TYPE_CHECKING:
    from gartenroboter.config.settings import DatabaseSettings

logger = logging.getLogger(__name__)

# SQL Schema definitions
SCHEMA_SQL = """
-- Sensor readings table
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    sensor_type TEXT NOT NULL,  -- 'soil_moisture', 'water_level', 'pi_temperature'
    zone_id INTEGER,  -- NULL for non-zone sensors
    raw_value INTEGER,
    normalized_value REAL,
    is_warning BOOLEAN DEFAULT FALSE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Pump events table
CREATE TABLE IF NOT EXISTS pump_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,  -- start/stop/error/cooldown_start/end
    zone_id INTEGER,
    duration_seconds REAL,
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Watering decisions table
CREATE TABLE IF NOT EXISTS watering_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    zone_id INTEGER NOT NULL,
    decision TEXT NOT NULL,  -- 'water', 'skip_not_dry', 'skip_before_sunset', etc.
    reason TEXT,
    soil_moisture_percent REAL,
    was_watered BOOLEAN DEFAULT FALSE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Weather data cache
CREATE TABLE IF NOT EXISTS weather_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    temperature_celsius REAL,
    humidity_percent REAL,
    description TEXT,
    wind_speed_ms REAL,
    clouds_percent INTEGER,
    rain_mm REAL,
    data_type TEXT DEFAULT 'current',  -- 'current' or 'forecast'
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Configuration changes log
CREATE TABLE IF NOT EXISTS config_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    changed_by TEXT,  -- chat_id or 'system'
    config_key TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Alerts/notifications sent
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    alert_type TEXT NOT NULL,  -- 'low_water', 'high_temp', 'watering_complete', etc.
    message TEXT,
    chat_id INTEGER,
    sent_successfully BOOLEAN DEFAULT TRUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_sensor_readings_timestamp ON sensor_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_sensor_readings_type ON sensor_readings(sensor_type);
CREATE INDEX IF NOT EXISTS idx_pump_events_timestamp ON pump_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_watering_ts ON watering_decisions(timestamp);
CREATE INDEX IF NOT EXISTS idx_weather_data_timestamp ON weather_data(timestamp);
CREATE INDEX IF NOT EXISTS idx_config_changes_timestamp ON config_changes(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
"""


@dataclass
class SensorReadingRow:
    """Database row for sensor reading."""

    id: int
    timestamp: datetime
    sensor_type: str
    zone_id: int | None
    raw_value: int | None
    normalized_value: float | None
    is_warning: bool


@dataclass
class PumpEventRow:
    """Database row for pump event."""

    id: int
    timestamp: datetime
    event_type: str
    zone_id: int | None
    duration_seconds: float | None
    reason: str | None


@dataclass
class WateringDecisionRow:
    """Database row for watering decision."""

    id: int
    timestamp: datetime
    zone_id: int
    decision: str
    reason: str | None
    soil_moisture_percent: float | None
    was_watered: bool


class Database:
    """Async SQLite database for Gartenroboter."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self.settings = settings
        self.db_path = Path(settings.path)
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Connect to database and initialize schema."""
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row

        # Initialize schema
        await self._connection.executescript(SCHEMA_SQL)
        await self._connection.commit()

        logger.info("Database connected: %s", self.db_path)

    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Database closed")

    async def _ensure_connected(self) -> aiosqlite.Connection:
        """Ensure connection is available."""
        if self._connection is None:
            await self.connect()
        return self._connection  # type: ignore

    # --- Sensor Readings ---

    async def insert_sensor_reading(
        self,
        sensor_type: str,
        raw_value: int | None,
        normalized_value: float | None,
        *,
        zone_id: int | None = None,
        is_warning: bool = False,
        timestamp: datetime | None = None,
    ) -> int:
        """Insert a sensor reading."""
        conn = await self._ensure_connected()
        ts = (timestamp or datetime.now(UTC)).isoformat()

        cursor = await conn.execute(
            """
            INSERT INTO sensor_readings
                (timestamp, sensor_type, zone_id, raw_value,
                 normalized_value, is_warning)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ts, sensor_type, zone_id, raw_value, normalized_value, is_warning),
        )
        await conn.commit()
        return cursor.lastrowid  # type: ignore

    async def get_sensor_readings(
        self,
        sensor_type: str | None = None,
        zone_id: int | None = None,
        hours: int = 24,
        limit: int = 1000,
    ) -> list[SensorReadingRow]:
        """Get sensor readings with optional filters."""
        conn = await self._ensure_connected()
        since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

        query = "SELECT * FROM sensor_readings WHERE timestamp > ?"
        params: list[Any] = [since]

        if sensor_type:
            query += " AND sensor_type = ?"
            params.append(sensor_type)

        if zone_id is not None:
            query += " AND zone_id = ?"
            params.append(zone_id)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [
                SensorReadingRow(
                    id=row["id"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    sensor_type=row["sensor_type"],
                    zone_id=row["zone_id"],
                    raw_value=row["raw_value"],
                    normalized_value=row["normalized_value"],
                    is_warning=bool(row["is_warning"]),
                )
                for row in rows
            ]

    async def get_latest_sensor_reading(
        self,
        sensor_type: str,
        zone_id: int | None = None,
    ) -> SensorReadingRow | None:
        """Get the most recent sensor reading."""
        readings = await self.get_sensor_readings(
            sensor_type=sensor_type,
            zone_id=zone_id,
            hours=24,
            limit=1,
        )
        return readings[0] if readings else None

    # --- Pump Events ---

    async def insert_pump_event(
        self,
        event_type: str,
        reason: str,
        *,
        zone_id: int | None = None,
        duration_seconds: float | None = None,
        timestamp: datetime | None = None,
    ) -> int:
        """Insert a pump event."""
        conn = await self._ensure_connected()
        ts = (timestamp or datetime.now(UTC)).isoformat()

        cursor = await conn.execute(
            """
            INSERT INTO pump_events 
                (timestamp, event_type, zone_id, duration_seconds, reason)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ts, event_type, zone_id, duration_seconds, reason),
        )
        await conn.commit()
        return cursor.lastrowid  # type: ignore

    async def get_pump_events(
        self,
        hours: int = 24,
        limit: int = 100,
    ) -> list[PumpEventRow]:
        """Get pump events."""
        conn = await self._ensure_connected()
        since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

        async with conn.execute(
            """
            SELECT * FROM pump_events 
            WHERE timestamp > ? 
            ORDER BY timestamp DESC 
            LIMIT ?
            """,
            (since, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                PumpEventRow(
                    id=row["id"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    event_type=row["event_type"],
                    zone_id=row["zone_id"],
                    duration_seconds=row["duration_seconds"],
                    reason=row["reason"],
                )
                for row in rows
            ]

    # --- Watering Decisions ---

    async def insert_watering_decision(
        self,
        zone_id: int,
        decision: str,
        reason: str,
        *,
        soil_moisture_percent: float | None = None,
        was_watered: bool = False,
        timestamp: datetime | None = None,
    ) -> int:
        """Insert a watering decision."""
        conn = await self._ensure_connected()
        ts = (timestamp or datetime.now(UTC)).isoformat()

        cursor = await conn.execute(
            """
            INSERT INTO watering_decisions
                (timestamp, zone_id, decision, reason,
                 soil_moisture_percent, was_watered)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ts, zone_id, decision, reason, soil_moisture_percent, was_watered),
        )
        await conn.commit()
        return cursor.lastrowid  # type: ignore

    async def get_watering_decisions(
        self,
        hours: int = 24,
        limit: int = 100,
    ) -> list[WateringDecisionRow]:
        """Get watering decisions."""
        conn = await self._ensure_connected()
        since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

        async with conn.execute(
            """
            SELECT * FROM watering_decisions 
            WHERE timestamp > ? 
            ORDER BY timestamp DESC 
            LIMIT ?
            """,
            (since, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                WateringDecisionRow(
                    id=row["id"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    zone_id=row["zone_id"],
                    decision=row["decision"],
                    reason=row["reason"],
                    soil_moisture_percent=row["soil_moisture_percent"],
                    was_watered=bool(row["was_watered"]),
                )
                for row in rows
            ]

    # --- Weather Data ---

    async def insert_weather_data(
        self,
        temperature_celsius: float,
        humidity_percent: float,
        description: str,
        wind_speed_ms: float,
        clouds_percent: int,
        rain_mm: float | None = None,
        data_type: str = "current",
        timestamp: datetime | None = None,
    ) -> int:
        """Insert weather data."""
        conn = await self._ensure_connected()
        ts = (timestamp or datetime.now(UTC)).isoformat()

        cursor = await conn.execute(
            """
            INSERT INTO weather_data 
                (timestamp, temperature_celsius, humidity_percent, description,
                 wind_speed_ms, clouds_percent, rain_mm, data_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                temperature_celsius,
                humidity_percent,
                description,
                wind_speed_ms,
                clouds_percent,
                rain_mm,
                data_type,
            ),
        )
        await conn.commit()
        return cursor.lastrowid  # type: ignore

    # --- Config Changes ---

    async def insert_config_change(
        self,
        config_key: str,
        old_value: Any,
        new_value: Any,
        changed_by: str = "system",
        timestamp: datetime | None = None,
    ) -> int:
        """Log a configuration change."""
        conn = await self._ensure_connected()
        ts = (timestamp or datetime.now(UTC)).isoformat()

        cursor = await conn.execute(
            """
            INSERT INTO config_changes 
                (timestamp, changed_by, config_key, old_value, new_value)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ts, changed_by, config_key, str(old_value), str(new_value)),
        )
        await conn.commit()
        return cursor.lastrowid  # type: ignore

    # --- Alerts ---

    async def insert_alert(
        self,
        alert_type: str,
        message: str,
        chat_id: int | None = None,
        sent_successfully: bool = True,
        timestamp: datetime | None = None,
    ) -> int:
        """Log an alert/notification."""
        conn = await self._ensure_connected()
        ts = (timestamp or datetime.now(UTC)).isoformat()

        cursor = await conn.execute(
            """
            INSERT INTO alerts 
                (timestamp, alert_type, message, chat_id, sent_successfully)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ts, alert_type, message, chat_id, sent_successfully),
        )
        await conn.commit()
        return cursor.lastrowid  # type: ignore

    # --- Statistics ---

    async def get_daily_statistics(
        self,
        date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get statistics for a day."""
        conn = await self._ensure_connected()

        if date is None:
            date = datetime.now(UTC)

        date_str = date.date().isoformat()
        start = f"{date_str}T00:00:00"
        end = f"{date_str}T23:59:59"

        # Count watering events
        async with conn.execute(
            """
            SELECT COUNT(*) as count, SUM(duration_seconds) as total_duration
            FROM pump_events 
            WHERE event_type = 'start' AND timestamp BETWEEN ? AND ?
            """,
            (start, end),
        ) as cursor:
            pump_row = await cursor.fetchone()

        # Average moisture per zone
        async with conn.execute(
            """
            SELECT zone_id, AVG(normalized_value) as avg_moisture
            FROM sensor_readings 
            WHERE sensor_type = 'soil_moisture' AND timestamp BETWEEN ? AND ?
            GROUP BY zone_id
            """,
            (start, end),
        ) as cursor:
            moisture_rows = await cursor.fetchall()

        return {
            "date": date_str,
            "watering_cycles": pump_row["count"] if pump_row else 0,
            "total_pump_runtime_seconds": pump_row["total_duration"] if pump_row else 0,
            "average_moisture_by_zone": {
                row["zone_id"]: round(row["avg_moisture"], 1) for row in moisture_rows
            },
        }
