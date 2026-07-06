"""
Tests for RuntimeMonitor, ExecutionMetrics, RuntimeStatistics, and AgentStatus.
"""

from __future__ import annotations

import pytest

from core.runtime import AgentRuntime, AgentState
from core.runtime_monitoring import (
    AgentStatus,
    ExecutionMetrics,
    RuntimeMonitor,
    RuntimeStatistics,
)


def test_execution_metrics_defaults() -> None:
    """ExecutionMetrics defaults are sensible."""
    m = ExecutionMetrics()
    assert m.execution_time_ms == 0.0
    assert m.success is False
    assert m.error is None


def test_agent_status_defaults() -> None:
    """AgentStatus defaults are sensible."""
    s = AgentStatus()
    assert s.agent_id == ""
    assert s.state == ""
    assert s.tasks_completed == 0
    assert s.tasks_failed == 0


def test_runtime_statistics_defaults() -> None:
    """RuntimeStatistics defaults are sensible."""
    s = RuntimeStatistics()
    assert s.total_sessions == 0
    assert s.failure_rate == 0.0
    assert s.average_execution_time_ms == 0.0


def test_monitor_records_session() -> None:
    """Monitor tracks session outcomes."""
    runtime = AgentRuntime()
    monitor = RuntimeMonitor(runtime)

    session = runtime.create_session("research", {"q": "test"})
    monitor.record_session_start(session)
    session.start()
    session.complete("answer")
    monitor.record_session_end(session)

    metrics = monitor.get_metrics(session.session_id)
    assert metrics is not None
    assert metrics.success is True
    assert metrics.execution_time_ms >= 0


def test_monitor_tracks_failures() -> None:
    """Monitor tracks failed sessions."""
    runtime = AgentRuntime()
    monitor = RuntimeMonitor(runtime)

    session = runtime.create_session("coding", {})
    session.start()
    session.fail("bug")
    monitor.record_session_end(session)

    metrics = monitor.get_metrics(session.session_id)
    assert metrics is not None
    assert metrics.success is False
    assert metrics.error == "bug"


def test_monitor_agent_status_idle() -> None:
    """Agent status is idle when no sessions are running."""
    runtime = AgentRuntime()
    monitor = RuntimeMonitor(runtime)
    status = monitor.get_agent_status("research")
    assert status.state == "idle"
    assert status.current_task is None


def test_monitor_agent_status_active() -> None:
    """Agent status is active when a session is running."""
    runtime = AgentRuntime()
    monitor = RuntimeMonitor(runtime)

    session = runtime.create_session("research", {"description": "find qubits"})
    session.start()
    monitor.record_session_start(session)

    status = monitor.get_agent_status("research")
    assert status.state == "active"
    assert status.current_task == "find qubits"


def test_monitor_statistics() -> None:
    """Statistics aggregate across all sessions."""
    runtime = AgentRuntime()
    monitor = RuntimeMonitor(runtime)

    s1 = runtime.create_session("research", {})
    s1.start()
    s1.complete("ok")
    monitor.record_session_end(s1)

    s2 = runtime.create_session("research", {})
    s2.start()
    s2.fail("err")
    monitor.record_session_end(s2)

    stats = monitor.get_statistics()
    assert stats.total_sessions == 2
    assert stats.completed_tasks == 1
    assert stats.failed_tasks == 1
    assert stats.failure_rate == 0.5


def test_monitor_clear() -> None:
    """Clear resets recorded metrics but leaves runtime sessions intact."""
    runtime = AgentRuntime()
    monitor = RuntimeMonitor(runtime)

    session = runtime.create_session("research", {})
    session.start()
    session.complete("ok")
    monitor.record_session_end(session)

    monitor.clear()
    assert monitor.get_metrics(session.session_id) is None
    # Runtime sessions are not owned by the monitor, so they remain
    assert monitor.get_statistics().total_sessions == 1


def test_monitor_uptime() -> None:
    """Uptime increases over time."""
    runtime = AgentRuntime()
    monitor = RuntimeMonitor(runtime)
    status = monitor.get_agent_status("research")
    assert status.uptime_seconds >= 0
