"""Unit tests for scheduler."""

import asyncio
from datetime import time
from unittest.mock import AsyncMock

import pytest

from gartenroboter.infra.scheduler import ScheduledTask, Scheduler


class TestScheduledTask:
    """Tests for ScheduledTask class."""

    @pytest.mark.asyncio
    async def test_interval_task_runs(self):
        """Test interval-based task runs at correct intervals."""
        call_count = 0

        async def task_func():
            nonlocal call_count
            call_count += 1

        task = ScheduledTask(
            name="test_task",
            coro_func=task_func,
            interval_seconds=0.1,
            run_immediately=True,
        )

        await task.start()
        await asyncio.sleep(0.35)
        await task.stop()

        # Should have run 3-4 times (immediately + 3 intervals)
        assert 3 <= call_count <= 5

    @pytest.mark.asyncio
    async def test_run_immediately_flag(self):
        """Test run_immediately flag behavior."""
        call_count = 0

        async def task_func():
            nonlocal call_count
            call_count += 1

        # With run_immediately=True
        task = ScheduledTask(
            name="test_task",
            coro_func=task_func,
            interval_seconds=10,  # Long interval
            run_immediately=True,
        )

        await task.start()
        await asyncio.sleep(0.05)  # Short wait
        await task.stop()

        assert call_count == 1  # Should have run once immediately

    @pytest.mark.asyncio
    async def test_task_error_handling(self):
        """Test task continues after errors."""
        call_count = 0

        async def failing_task():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Test error")

        task = ScheduledTask(
            name="failing_task",
            coro_func=failing_task,
            interval_seconds=0.05,
            run_immediately=True,
        )

        await task.start()
        await asyncio.sleep(0.2)
        await task.stop()

        # Should have continued running despite errors
        assert call_count >= 3
        assert task._error_count >= 2

    @pytest.mark.asyncio
    async def test_task_stats(self):
        """Test task statistics."""

        async def task_func():
            pass

        task = ScheduledTask(
            name="stats_task",
            coro_func=task_func,
            interval_seconds=0.05,
            run_immediately=True,
        )

        await task.start()
        await asyncio.sleep(0.15)
        await task.stop()

        stats = task.stats
        assert stats["name"] == "stats_task"
        assert stats["run_count"] >= 2
        assert stats["error_count"] == 0
        assert stats["last_run"] is not None

    def test_requires_interval_or_daily(self):
        """Test task requires either interval or daily_at."""
        with pytest.raises(ValueError, match="Must specify"):
            ScheduledTask(
                name="invalid_task",
                coro_func=AsyncMock(),
            )

    def test_cannot_have_both_interval_and_daily(self):
        """Test task cannot have both interval and daily_at."""
        with pytest.raises(ValueError, match="Cannot specify both"):
            ScheduledTask(
                name="invalid_task",
                coro_func=AsyncMock(),
                interval_seconds=60,
                daily_at=time(12, 0),
            )


class TestScheduler:
    """Tests for Scheduler class."""

    @pytest.fixture
    def scheduler(self) -> Scheduler:
        """Create scheduler instance."""
        return Scheduler()

    def test_add_task(self, scheduler: Scheduler):
        """Test adding tasks to scheduler."""
        mock_func = AsyncMock()

        task = scheduler.add_task(
            name="test_task",
            coro_func=mock_func,
            interval_seconds=60,
        )

        assert task is not None
        assert scheduler.get_task("test_task") is task

    def test_add_duplicate_task_fails(self, scheduler: Scheduler):
        """Test adding duplicate task name fails."""
        mock_func = AsyncMock()

        scheduler.add_task(
            name="test_task",
            coro_func=mock_func,
            interval_seconds=60,
        )

        with pytest.raises(ValueError, match="already exists"):
            scheduler.add_task(
                name="test_task",
                coro_func=mock_func,
                interval_seconds=60,
            )

    @pytest.mark.asyncio
    async def test_start_stop_scheduler(self, scheduler: Scheduler):
        """Test starting and stopping scheduler."""
        mock_func = AsyncMock()

        scheduler.add_task(
            name="test_task",
            coro_func=mock_func,
            interval_seconds=0.1,
        )

        assert not scheduler.is_running

        await scheduler.start()
        assert scheduler.is_running

        await asyncio.sleep(0.15)

        await scheduler.stop()
        assert not scheduler.is_running

    @pytest.mark.asyncio
    async def test_run_task_now(self, scheduler: Scheduler):
        """Test manually triggering a task."""
        call_count = 0

        async def task_func():
            nonlocal call_count
            call_count += 1

        scheduler.add_task(
            name="manual_task",
            coro_func=task_func,
            interval_seconds=60,
            run_immediately=False,
        )

        await scheduler.start()

        # Manually trigger
        await scheduler.run_task_now("manual_task")

        assert call_count == 1

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_run_task_now_not_found(self, scheduler: Scheduler):
        """Test running non-existent task."""
        with pytest.raises(ValueError, match="not found"):
            await scheduler.run_task_now("nonexistent")

    def test_get_stats(self, scheduler: Scheduler):
        """Test getting scheduler statistics."""
        scheduler.add_task(
            name="task1",
            coro_func=AsyncMock(),
            interval_seconds=60,
        )
        scheduler.add_task(
            name="task2",
            coro_func=AsyncMock(),
            interval_seconds=120,
        )

        stats = scheduler.get_stats()

        assert stats["task_count"] == 2
        assert "task1" in stats["tasks"]
        assert "task2" in stats["tasks"]

    @pytest.mark.asyncio
    async def test_remove_task(self, scheduler: Scheduler):
        """Test removing a task."""
        scheduler.add_task(
            name="removable_task",
            coro_func=AsyncMock(),
            interval_seconds=60,
        )

        assert scheduler.get_task("removable_task") is not None

        scheduler.remove_task("removable_task")

        assert scheduler.get_task("removable_task") is None
