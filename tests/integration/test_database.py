"""Integration tests for database operations."""

from datetime import datetime, timedelta

import pytest

from gartenroboter.infra.database import Database


class TestDatabaseIntegration:
    """Integration tests for Database class."""

    @pytest.mark.asyncio
    async def test_database_initialization(self, temp_database_file):
        """Test database initializes with correct schema."""
        db = Database(temp_database_file)
        await db.initialize()

        # Verify database file was created
        assert temp_database_file.exists()

        await db.close()

    @pytest.mark.asyncio
    async def test_log_and_retrieve_sensor_reading(self, initialized_database):
        """Test logging and retrieving sensor readings."""
        db = initialized_database

        # Log a reading
        await db.log_sensor_reading(
            soil_moisture=[30.0, 45.0, 60.0, 75.0],
            water_level=85.0,
            pi_temperature=45.0,
        )

        # Retrieve readings
        readings = await db.get_sensor_readings(limit=10)

        assert len(readings) == 1
        reading = readings[0]
        assert reading.soil_moisture == [30.0, 45.0, 60.0, 75.0]
        assert reading.water_level == 85.0
        assert reading.pi_temperature == 45.0

    @pytest.mark.asyncio
    async def test_log_pump_event(self, initialized_database):
        """Test logging pump events."""
        db = initialized_database

        await db.log_pump_event(
            event_type="start",
            zone=1,
            duration_seconds=120.0,
            reason="Soil dry in zone 1",
        )

        events = await db.get_pump_events(limit=10)

        assert len(events) == 1
        event = events[0]
        assert event.event_type == "start"
        assert event.zone == 1
        assert event.duration_seconds == 120.0

    @pytest.mark.asyncio
    async def test_log_alert(self, initialized_database):
        """Test logging alerts."""
        db = initialized_database

        await db.log_alert(
            alert_type="water_level_low",
            message="Water level below 20%",
            severity="warning",
        )

        alerts = await db.get_alerts(limit=10)

        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.alert_type == "water_level_low"
        assert alert.severity == "warning"

    @pytest.mark.asyncio
    async def test_data_rotation(self, initialized_database):
        """Test data rotation removes old records."""
        db = initialized_database

        # Insert old and new readings directly
        async with db._connection.execute(
            """
            INSERT INTO sensor_readings
                (timestamp, soil_moisture, water_level, pi_temperature)
            VALUES (?, ?, ?, ?)
            """,
            (
                (datetime.now() - timedelta(days=100)).isoformat(),
                "[30, 40, 50, 60]",
                85.0,
                45.0,
            ),
        ):
            pass

        await db._connection.commit()

        # Log a current reading
        await db.log_sensor_reading(
            soil_moisture=[35.0, 45.0, 55.0, 65.0],
            water_level=80.0,
            pi_temperature=50.0,
        )

        # Rotate with 90-day retention
        deleted = await db.rotate_data(retention_days=90)

        assert deleted >= 1

        # Only new reading should remain
        readings = await db.get_sensor_readings(limit=10)
        assert len(readings) == 1

    @pytest.mark.asyncio
    async def test_get_readings_with_since_filter(self, initialized_database):
        """Test filtering readings by timestamp."""
        db = initialized_database

        # Log multiple readings
        for i in range(5):
            await db.log_sensor_reading(
                soil_moisture=[30.0 + i, 40.0, 50.0, 60.0],
                water_level=80.0,
                pi_temperature=45.0,
            )

        # Get readings from the last hour
        since = datetime.now() - timedelta(hours=1)
        readings = await db.get_sensor_readings(since=since)

        assert len(readings) == 5

    @pytest.mark.asyncio
    async def test_concurrent_writes(self, initialized_database):
        """Test database handles concurrent writes."""
        import asyncio

        db = initialized_database

        async def write_reading(i: int):
            await db.log_sensor_reading(
                soil_moisture=[float(i), 40.0, 50.0, 60.0],
                water_level=80.0,
                pi_temperature=45.0,
            )

        # Write 10 readings concurrently
        await asyncio.gather(*[write_reading(i) for i in range(10)])

        # All should be written
        readings = await db.get_sensor_readings(limit=20)
        assert len(readings) == 10
