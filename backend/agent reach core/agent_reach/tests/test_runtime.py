"""
Tests for the Agent Runtime layer.

Covers AgentState, AgentContext, AgentSession, and AgentRuntime.
"""

from __future__ import annotations

import pytest

from core.runtime import AgentContext, AgentRuntime, AgentSession, AgentState


def test_agent_state_values() -> None:
    """AgentState covers the expected lifecycle states."""
    assert AgentState.IDLE.value == "idle"
    assert AgentState.RUNNING.value == "running"
    assert AgentState.PAUSED.value == "paused"
    assert AgentState.COMPLETED.value == "completed"
    assert AgentState.FAILED.value == "failed"
    assert AgentState.CANCELLED.value == "cancelled"


def test_agent_context_defaults() -> None:
    """AgentContext generates a session_id and empty containers by default."""
    ctx = AgentContext()
    assert ctx.session_id
    assert ctx.agent_type == ""
    assert ctx.input_data == {}
    assert ctx.memory == {}
    assert ctx.metadata == {}


def test_agent_context_with_data() -> None:
    """AgentContext accepts explicit fields."""
    ctx = AgentContext(agent_type="research", input_data={"q": "test"})
    assert ctx.agent_type == "research"
    assert ctx.input_data == {"q": "test"}


def test_session_lifecycle_success() -> None:
    """A session transitions IDLE → RUNNING → COMPLETED."""
    session = AgentSession(AgentContext())
    assert session.state == AgentState.IDLE

    session.start()
    assert session.state == AgentState.RUNNING

    session.complete({"answer": "42"})
    assert session.state == AgentState.COMPLETED
    assert session.result == {"answer": "42"}
    assert session.metadata.duration_ms is not None
    assert session.metadata.duration_ms >= 0


def test_session_lifecycle_failure() -> None:
    """A session transitions IDLE → RUNNING → FAILED."""
    session = AgentSession(AgentContext())
    session.start()
    session.fail("something went wrong")
    assert session.state == AgentState.FAILED
    assert session.metadata.error == "something went wrong"


def test_session_cancellation() -> None:
    """A running session can be cancelled."""
    session = AgentSession(AgentContext())
    session.start()
    session.cancel()
    assert session.state == AgentState.CANCELLED
    assert session.is_cancelled()
    assert session.metadata.error == "cancelled"


def test_session_cancel_when_idle() -> None:
    """Cancelling an idle session sets the flag but does not change state."""
    session = AgentSession(AgentContext())
    session.cancel()
    assert session.is_cancelled()
    assert session.state == AgentState.IDLE


def test_session_start_from_non_idle_raises() -> None:
    """Starting a session that is not IDLE is an error."""
    session = AgentSession(AgentContext())
    session.start()
    with pytest.raises(RuntimeError):
        session.start()


def test_session_complete_from_non_running_raises() -> None:
    """Completing a session that is not RUNNING is an error."""
    session = AgentSession(AgentContext())
    with pytest.raises(RuntimeError):
        session.complete({})


def test_session_fail_from_non_running_raises() -> None:
    """Failing a session that is not RUNNING is an error."""
    session = AgentSession(AgentContext())
    with pytest.raises(RuntimeError):
        session.fail("error")


def test_runtime_create_session() -> None:
    """Runtime creates and tracks sessions."""
    runtime = AgentRuntime()
    session = runtime.create_session("research", {"q": "hello"})
    assert session.session_id in {s.session_id for s in runtime.list_sessions()}
    assert session.context.agent_type == "research"


def test_runtime_get_session() -> None:
    """Runtime retrieves sessions by ID."""
    runtime = AgentRuntime()
    session = runtime.create_session("coding", {})
    retrieved = runtime.get_session(session.session_id)
    assert retrieved is session


def test_runtime_get_missing_session() -> None:
    """Runtime returns None for unknown session IDs."""
    runtime = AgentRuntime()
    assert runtime.get_session("nonexistent") is None


def test_runtime_list_by_state() -> None:
    """Runtime filters sessions by state."""
    runtime = AgentRuntime()
    s1 = runtime.create_session("research", {})
    s2 = runtime.create_session("coding", {})
    s1.start()
    s1.complete("done")
    s2.start()

    completed = runtime.list_sessions_by_state(AgentState.COMPLETED)
    running = runtime.list_sessions_by_state(AgentState.RUNNING)

    assert len(completed) == 1
    assert len(running) == 1


def test_runtime_destroy_session() -> None:
    """Runtime removes sessions."""
    runtime = AgentRuntime()
    session = runtime.create_session("research", {})
    assert runtime.destroy_session(session.session_id) is True
    assert runtime.get_session(session.session_id) is None


def test_runtime_destroy_missing_session() -> None:
    """Destroying a non-existent session returns False."""
    runtime = AgentRuntime()
    assert runtime.destroy_session("nonexistent") is False


def test_runtime_clear() -> None:
    """Runtime clears all sessions."""
    runtime = AgentRuntime()
    runtime.create_session("research", {})
    runtime.create_session("coding", {})
    runtime.clear()
    assert runtime.list_sessions() == []
