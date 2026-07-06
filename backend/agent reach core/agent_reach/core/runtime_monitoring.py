"""
Runtime Monitoring layer for Milestone 3.

Tracks execution metrics, runtime statistics, and agent status.

Layer: Application/Core — depends inward on core/runtime only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from core.runtime import AgentRuntime, AgentSession, AgentState


@dataclass
class ExecutionMetrics:
    """Metrics for a single execution."""

    execution_time_ms: float = 0.0
    success: bool = False
    error: Optional[str] = None


@dataclass
class AgentStatus:
    """Current status of an agent in the runtime."""

    agent_id: str = ""
    agent_type: str = ""
    state: str = ""
    current_task: Optional[str] = None
    uptime_seconds: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0


@dataclass
class RuntimeStatistics:
    """Aggregated statistics across the runtime."""

    total_sessions: int = 0
    active_sessions: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_execution_time_ms: float = 0.0
    average_execution_time_ms: float = 0.0
    failure_rate: float = 0.0


class RuntimeMonitor:
    """Monitors and reports on AgentRuntime activity.

    Tracks:
    - execution time per session
    - failures and completions
    - active session counts
    - per-agent status
    """

    def __init__(self, runtime: AgentRuntime) -> None:
        self._runtime = runtime
        self._metrics: dict[str, ExecutionMetrics] = {}
        self._agent_stats: dict[str, dict[str, Any]] = {}
        self._start_time = time.perf_counter()

    def record_session_start(self, session: AgentSession) -> None:
        """Record that a session has started."""
        agent_type = session.context.agent_type
        if agent_type not in self._agent_stats:
            self._agent_stats[agent_type] = {
                "tasks_completed": 0,
                "tasks_failed": 0,
                "total_time_ms": 0.0,
            }

    def record_session_end(self, session: AgentSession) -> None:
        """Record the outcome of a completed session."""
        agent_type = session.context.agent_type
        duration = session.metadata.duration_ms or 0.0

        self._metrics[session.session_id] = ExecutionMetrics(
            execution_time_ms=duration,
            success=session.state == AgentState.COMPLETED,
            error=session.metadata.error,
        )

        stats = self._agent_stats.setdefault(
            agent_type,
            {"tasks_completed": 0, "tasks_failed": 0, "total_time_ms": 0.0},
        )
        stats["total_time_ms"] += duration

        if session.state == AgentState.COMPLETED:
            stats["tasks_completed"] += 1
        elif session.state in (AgentState.FAILED, AgentState.CANCELLED):
            stats["tasks_failed"] += 1

    def get_agent_status(self, agent_type: str) -> AgentStatus:
        """Get current status for an agent type."""
        stats = self._agent_stats.get(agent_type, {})
        sessions = self._runtime.list_sessions()
        active = [s for s in sessions if s.context.agent_type == agent_type and s.state == AgentState.RUNNING]

        return AgentStatus(
            agent_id=agent_type,
            agent_type=agent_type,
            state="active" if active else "idle",
            current_task=active[0].context.input_data.get("description") if active else None,
            uptime_seconds=time.perf_counter() - self._start_time,
            tasks_completed=stats.get("tasks_completed", 0),
            tasks_failed=stats.get("tasks_failed", 0),
        )

    def get_statistics(self) -> RuntimeStatistics:
        """Get aggregated runtime statistics."""
        sessions = self._runtime.list_sessions()
        completed = sum(1 for s in sessions if s.state == AgentState.COMPLETED)
        failed = sum(1 for s in sessions if s.state in (AgentState.FAILED, AgentState.CANCELLED))
        active = sum(1 for s in sessions if s.state == AgentState.RUNNING)
        total_time = sum(m.execution_time_ms for m in self._metrics.values())
        total_tasks = completed + failed

        return RuntimeStatistics(
            total_sessions=len(sessions),
            active_sessions=active,
            completed_tasks=completed,
            failed_tasks=failed,
            total_execution_time_ms=total_time,
            average_execution_time_ms=total_time / total_tasks if total_tasks > 0 else 0.0,
            failure_rate=failed / total_tasks if total_tasks > 0 else 0.0,
        )

    def get_metrics(self, session_id: str) -> Optional[ExecutionMetrics]:
        """Get metrics for a specific session."""
        return self._metrics.get(session_id)

    def clear(self) -> None:
        """Clear all recorded metrics."""
        self._metrics.clear()
        self._agent_stats.clear()
        self._start_time = time.perf_counter()
