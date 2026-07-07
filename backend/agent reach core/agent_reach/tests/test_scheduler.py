"""Tests for Scheduler (M4.11)."""

from __future__ import annotations

import asyncio
import time

import pytest

from core.scheduler import Scheduler


async def _task_executor(value: int = 0) -> int:
    return value * 2


async def _fail_executor() -> None:
    raise RuntimeError("boom")


class TestScheduler:
    def test_schedule_and_get(self) -> None:
        scheduler = Scheduler()
        task_id = scheduler.schedule(_task_executor, {"value": 5})
        task = scheduler.get_task(task_id)
        assert task is not None
        assert task.payload == {"value": 5}
        assert task.priority == 0

    def test_schedule_with_delay(self) -> None:
        scheduler = Scheduler()
        task_id = scheduler.schedule(_task_executor, delay_seconds=10.0)
        task = scheduler.get_task(task_id)
        assert task.execute_at > time.perf_counter()

    def test_cancel(self) -> None:
        scheduler = Scheduler()
        task_id = scheduler.schedule(_task_executor)
        assert scheduler.cancel(task_id) is True
        assert scheduler.get_task(task_id).cancelled is True
        assert scheduler.cancel("missing") is False

    def test_pending_count(self) -> None:
        scheduler = Scheduler()
        scheduler.schedule(_task_executor)
        scheduler.schedule(_task_executor)
        assert scheduler.pending_count() == 2

    def test_next_ready_with_delay(self) -> None:
        scheduler = Scheduler()
        scheduler.schedule(_task_executor, delay_seconds=3600)
        assert scheduler.next_ready_task() is None

    @pytest.mark.asyncio
    async def test_run_next_success(self) -> None:
        scheduler = Scheduler()
        scheduler.schedule(_task_executor, {"value": 3})
        result = await scheduler.run_next()
        assert result is not None
        assert result.success is True
        assert result.output == 6

    @pytest.mark.asyncio
    async def test_run_next_failure(self) -> None:
        scheduler = Scheduler()
        scheduler.schedule(_fail_executor)
        result = await scheduler.run_next()
        assert result is not None
        assert result.success is False
        assert "boom" in result.error

    @pytest.mark.asyncio
    async def test_run_next_none_when_empty(self) -> None:
        scheduler = Scheduler()
        result = await scheduler.run_next()
        assert result is None

    @pytest.mark.asyncio
    async def test_run_all(self) -> None:
        scheduler = Scheduler()
        scheduler.schedule(_task_executor, {"value": 1}, priority=1)
        scheduler.schedule(_task_executor, {"value": 2}, priority=0)
        results = await scheduler.run_all()
        assert len(results) == 2
        outputs = {r.output for r in results}
        assert outputs == {2, 4}

    @pytest.mark.asyncio
    async def test_cancelled_task_skipped(self) -> None:
        scheduler = Scheduler()
        task_id = scheduler.schedule(_task_executor, {"value": 5})
        scheduler.cancel(task_id)
        result = await scheduler.run_next()
        assert result is None

    def test_clear(self) -> None:
        scheduler = Scheduler()
        scheduler.schedule(_task_executor)
        scheduler.clear()
        assert scheduler.pending_count() == 0
        assert scheduler.list_tasks() == []
