"""
Scheduler for Milestone 4.

Provides in-process task scheduling with:
- Priority queue (lower number = higher priority)
- Delayed execution (execute_at timestamp)
- Task cancellation
- Sequential execution of scheduled tasks

Per the Milestone 4 directive: no distributed networking.
Everything is in-process only.

Layer: Application/Core — depends inward on domain/ and infrastructure/ only.
"""

from __future__ import annotations

import heapq
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


@dataclass
class ScheduledTask:
    """A task waiting to be executed by the Scheduler."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: int = 0  # lower is higher priority
    execute_at: float = field(default_factory=time.perf_counter)
    payload: dict[str, Any] = field(default_factory=dict)
    executor: Callable[..., Awaitable[Any]] = field(default=lambda **kwargs: None)
    cancelled: bool = False

    # For heapq comparison
    def __lt__(self, other: ScheduledTask) -> bool:
        if self.execute_at != other.execute_at:
            return self.execute_at < other.execute_at
        return self.priority < other.priority


@dataclass
class ScheduleResult:
    """Outcome of executing a scheduled task."""

    task_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0


class Scheduler:
    """In-process scheduler with priority queue and delayed execution.

    Tasks are stored in a min-heap ordered by execute_at time, then
    by priority. The scheduler can run tasks sequentially or return
    the next ready task for external execution.
    """

    def __init__(self) -> None:
        self._queue: list[ScheduledTask] = []
        self._tasks: dict[str, ScheduledTask] = {}

    def schedule(
        self,
        executor: Callable[..., Awaitable[Any]],
        payload: dict[str, Any] | None = None,
        priority: int = 0,
        delay_seconds: float = 0.0,
    ) -> str:
        """Schedule a new task.

        Args:
            executor: Async callable to execute
            payload: Arguments passed to the executor
            priority: Lower numbers run first (if same time)
            delay_seconds: How long to wait before execution

        Returns:
            The scheduled task ID
        """
        task = ScheduledTask(
            priority=priority,
            execute_at=time.perf_counter() + delay_seconds,
            payload=payload or {},
            executor=executor,
        )
        heapq.heappush(self._queue, task)
        self._tasks[task.task_id] = task
        return task.task_id

    def cancel(self, task_id: str) -> bool:
        """Cancel a scheduled task.

        Returns:
            True if the task was found and cancelled
        """
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.cancelled = True
        return True

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Retrieve a task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[ScheduledTask]:
        """List all tasks (including executed and cancelled)."""
        return list(self._tasks.values())

    def pending_count(self) -> int:
        """Return the number of non-cancelled tasks still in the queue."""
        return sum(1 for t in self._queue if not t.cancelled)

    def next_ready_task(self) -> Optional[ScheduledTask]:
        """Return the next task that is ready to execute.

        Removes cancelled tasks from the front of the queue.
        """
        now = time.perf_counter()
        while self._queue:
            task = self._queue[0]
            if task.cancelled:
                heapq.heappop(self._queue)
                continue
            if task.execute_at <= now:
                return heapq.heappop(self._queue)
            return None
        return None

    async def run_next(self) -> Optional[ScheduleResult]:
        """Execute the next ready task and return its result."""
        task = self.next_ready_task()
        if task is None:
            return None

        start = time.perf_counter()
        try:
            output = await task.executor(**task.payload)
            return ScheduleResult(
                task_id=task.task_id,
                success=True,
                output=output,
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as exc:
            return ScheduleResult(
                task_id=task.task_id,
                success=False,
                error=f"Execution failed: {exc}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

    async def run_all(self) -> list[ScheduleResult]:
        """Execute all ready tasks and return their results."""
        results: list[ScheduleResult] = []
        while True:
            result = await self.run_next()
            if result is None:
                break
            results.append(result)
        return results

    def clear(self) -> None:
        """Remove all tasks. Useful for testing."""
        self._queue.clear()
        self._tasks.clear()
