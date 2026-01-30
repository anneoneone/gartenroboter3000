"""Scheduler for managing background tasks."""

import asyncio
import contextlib
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime, time
from typing import Any

logger = logging.getLogger(__name__)


class ScheduledTask:
    """A scheduled task with interval or daily schedule."""

    def __init__(
        self,
        name: str,
        coro_func: Callable[[], Coroutine[Any, Any, Any]],
        interval_seconds: float | None = None,
        daily_at: time | None = None,
        run_immediately: bool = False,
    ):
        """Initialize scheduled task.

        Args:
            name: Task name for logging
            coro_func: Async function to run (no arguments)
            interval_seconds: Run every N seconds (exclusive with daily_at)
            daily_at: Run once daily at this time (exclusive with interval)
            run_immediately: If True, run once immediately on start
        """
        if interval_seconds is None and daily_at is None:
            raise ValueError("Must specify either interval_seconds or daily_at")
        if interval_seconds is not None and daily_at is not None:
            raise ValueError("Cannot specify both interval_seconds and daily_at")

        self.name = name
        self.coro_func = coro_func
        self.interval_seconds = interval_seconds
        self.daily_at = daily_at
        self.run_immediately = run_immediately

        self._task: asyncio.Task | None = None
        self._running = False
        self._last_run: datetime | None = None
        self._run_count = 0
        self._error_count = 0

    @property
    def is_running(self) -> bool:
        """Check if task is currently running."""
        return self._running

    @property
    def last_run(self) -> datetime | None:
        """Get last run timestamp."""
        return self._last_run

    @property
    def stats(self) -> dict[str, Any]:
        """Get task statistics."""
        return {
            "name": self.name,
            "running": self._running,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "run_count": self._run_count,
            "error_count": self._error_count,
        }

    async def start(self) -> None:
        """Start the scheduled task."""
        if self._running:
            return

        self._running = True

        if self.interval_seconds is not None:
            self._task = asyncio.create_task(self._run_interval())
        else:
            self._task = asyncio.create_task(self._run_daily())

        logger.info(f"Started scheduled task: {self.name}")

    async def stop(self) -> None:
        """Stop the scheduled task."""
        self._running = False

        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task

        logger.info(f"Stopped scheduled task: {self.name}")

    async def _run_interval(self) -> None:
        """Run task at regular intervals."""
        # Run immediately if requested
        if self.run_immediately:
            await self._execute()

        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)

                if self._running:
                    await self._execute()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._error_count += 1
                logger.error(f"Error in scheduled task {self.name}: {e}")
                # Continue running despite errors
                await asyncio.sleep(1)

    async def _run_daily(self) -> None:
        """Run task once daily at specified time."""
        while self._running:
            try:
                # Calculate time until next run
                now = datetime.now()
                target_time = datetime.combine(now.date(), self.daily_at)

                if now >= target_time:
                    # Already passed today, schedule for tomorrow
                    target_time = datetime.combine(now.date(), self.daily_at).replace(
                        day=now.day + 1
                    )

                sleep_seconds = (target_time - now).total_seconds()
                logger.debug(
                    f"Task {self.name} scheduled for {target_time}, "
                    f"sleeping {sleep_seconds:.0f}s"
                )

                await asyncio.sleep(sleep_seconds)

                if self._running:
                    await self._execute()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._error_count += 1
                logger.error(f"Error in scheduled task {self.name}: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying

    async def _execute(self) -> None:
        """Execute the task function."""
        try:
            logger.debug(f"Running scheduled task: {self.name}")
            await self.coro_func()
            self._last_run = datetime.now()
            self._run_count += 1
            logger.debug(f"Completed scheduled task: {self.name}")
        except Exception as e:
            self._error_count += 1
            logger.error(f"Task {self.name} failed: {e}", exc_info=True)
            # Don't re-raise - allow the scheduler to continue


class Scheduler:
    """Manage multiple scheduled tasks.

    Provides a centralized way to manage background tasks for:
    - Sensor polling (every 30s)
    - Watering checks (every 5 min)
    - Data rotation (daily at midnight)
    - Temperature monitoring (every 60s)
    - Weather updates (every 10 min)
    """

    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._pending_starts: list[asyncio.Task[None]] = []
        self._pending_stops: list[asyncio.Task[None]] = []

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running

    def add_task(
        self,
        name: str,
        coro_func: Callable[[], Coroutine[Any, Any, Any]],
        interval_seconds: float | None = None,
        daily_at: time | None = None,
        run_immediately: bool = False,
    ) -> ScheduledTask:
        """Add a new scheduled task.

        Args:
            name: Unique task name
            coro_func: Async function to run
            interval_seconds: Run every N seconds
            daily_at: Run once daily at this time
            run_immediately: Run once immediately on start

        Returns:
            The created ScheduledTask
        """
        if name in self._tasks:
            raise ValueError(f"Task '{name}' already exists")

        task = ScheduledTask(
            name=name,
            coro_func=coro_func,
            interval_seconds=interval_seconds,
            daily_at=daily_at,
            run_immediately=run_immediately,
        )
        self._tasks[name] = task

        # Start immediately if scheduler is already running
        if self._running:
            start_task = asyncio.create_task(task.start())
            self._pending_starts.append(start_task)

        return task

    def remove_task(self, name: str) -> None:
        """Remove a scheduled task."""
        if name not in self._tasks:
            return

        task = self._tasks.pop(name)
        stop_task = asyncio.create_task(task.stop())
        self._pending_stops.append(stop_task)

    def get_task(self, name: str) -> ScheduledTask | None:
        """Get a task by name."""
        return self._tasks.get(name)

    def get_stats(self) -> dict[str, Any]:
        """Get statistics for all tasks."""
        return {
            "running": self._running,
            "task_count": len(self._tasks),
            "tasks": {name: task.stats for name, task in self._tasks.items()},
        }

    async def start(self) -> None:
        """Start all scheduled tasks."""
        if self._running:
            return

        self._running = True
        logger.info(f"Starting scheduler with {len(self._tasks)} tasks")

        # Start all tasks concurrently
        await asyncio.gather(
            *[task.start() for task in self._tasks.values()], return_exceptions=True
        )

        logger.info("Scheduler started")

    async def stop(self) -> None:
        """Stop all scheduled tasks."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping scheduler...")

        # Stop all tasks concurrently
        await asyncio.gather(
            *[task.stop() for task in self._tasks.values()], return_exceptions=True
        )

        logger.info("Scheduler stopped")

    async def run_task_now(self, name: str) -> None:
        """Manually trigger a task to run immediately."""
        task = self._tasks.get(name)
        if task:
            await task._execute()
        else:
            raise ValueError(f"Task '{name}' not found")


def create_default_scheduler(
    sensor_callback: Callable[[], Coroutine[Any, Any, Any]],
    watering_callback: Callable[[], Coroutine[Any, Any, Any]],
    rotation_callback: Callable[[], Coroutine[Any, Any, Any]],
    temperature_callback: Callable[[], Coroutine[Any, Any, Any]],
    weather_callback: Callable[[], Coroutine[Any, Any, Any]] | None = None,
) -> Scheduler:
    """Create scheduler with default tasks for Gartenroboter3000.

    Args:
        sensor_callback: Called every 30s to read sensors
        watering_callback: Called every 5 min to check watering
        rotation_callback: Called daily at midnight for data rotation
        temperature_callback: Called every 60s to check Pi temperature
        weather_callback: Called every 10 min to update weather (optional)

    Returns:
        Configured Scheduler instance
    """
    scheduler = Scheduler()

    # Sensor polling - every 30 seconds
    scheduler.add_task(
        name="sensor_polling",
        coro_func=sensor_callback,
        interval_seconds=30,
        run_immediately=True,
    )

    # Watering check - every 5 minutes
    scheduler.add_task(
        name="watering_check",
        coro_func=watering_callback,
        interval_seconds=300,
        run_immediately=False,
    )

    # Data rotation - daily at midnight
    scheduler.add_task(
        name="data_rotation",
        coro_func=rotation_callback,
        daily_at=time(0, 0, 0),
    )

    # Temperature monitoring - every 60 seconds
    scheduler.add_task(
        name="temperature_monitor",
        coro_func=temperature_callback,
        interval_seconds=60,
        run_immediately=True,
    )

    # Weather updates - every 10 minutes (optional)
    if weather_callback:
        scheduler.add_task(
            name="weather_update",
            coro_func=weather_callback,
            interval_seconds=600,
            run_immediately=True,
        )

    return scheduler
