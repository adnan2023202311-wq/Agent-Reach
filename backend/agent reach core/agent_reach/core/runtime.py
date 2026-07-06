"""
Agent Runtime layer.

Manages the lifecycle of agent execution:
- AgentRuntime: global runtime coordinator
- AgentSession: single execution context
- AgentContext: input data and metadata for one run
- AgentState: execution state machine

Layer: Application/Core — depends inward on domain/ and infrastructure/ only.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AgentState(str, Enum):
    """Finite state machine for agent execution."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentContext:
    """Immutable context for a single agent execution."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_type: str = ""
    input_data: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionMetadata:
    """Metadata captured during execution."""

    started_at: float = field(default_factory=time.perf_counter)
    finished_at: Optional[float] = None
    duration_ms: Optional[float] = None
    attempts: int = 0
    error: Optional[str] = None

    def finalize(self, error: Optional[str] = None) -> None:
        """Mark execution as finished and compute duration."""
        self.finished_at = time.perf_counter()
        self.duration_ms = (self.finished_at - self.started_at) * 1000
        if error:
            self.error = error


class AgentSession:
    """Manages the lifecycle of one agent execution session."""

    def __init__(self, context: AgentContext) -> None:
        self._context = context
        self._state = AgentState.IDLE
        self._result: Any = None
        self._metadata = ExecutionMetadata()
        self._cancelled = False

    @property
    def session_id(self) -> str:
        return self._context.session_id

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def context(self) -> AgentContext:
        return self._context

    @property
    def result(self) -> Any:
        return self._result

    @property
    def metadata(self) -> ExecutionMetadata:
        return self._metadata

    def start(self) -> None:
        """Transition from IDLE to RUNNING."""
        if self._state != AgentState.IDLE:
            raise RuntimeError(f"Cannot start session from state {self._state.value}")
        self._state = AgentState.RUNNING
        self._metadata = ExecutionMetadata()

    def complete(self, result: Any) -> None:
        """Transition from RUNNING to COMPLETED."""
        if self._state != AgentState.RUNNING:
            raise RuntimeError(f"Cannot complete session from state {self._state.value}")
        self._result = result
        self._state = AgentState.COMPLETED
        self._metadata.finalize()

    def fail(self, error: str) -> None:
        """Transition from RUNNING to FAILED."""
        if self._state != AgentState.RUNNING:
            raise RuntimeError(f"Cannot fail session from state {self._state.value}")
        self._state = AgentState.FAILED
        self._metadata.finalize(error=error)

    def cancel(self) -> None:
        """Request cancellation and transition to CANCELLED."""
        self._cancelled = True
        if self._state == AgentState.RUNNING:
            self._state = AgentState.CANCELLED
            self._metadata.finalize(error="cancelled")

    def is_cancelled(self) -> bool:
        return self._cancelled


class AgentRuntime:
    """Global coordinator for agent execution sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}

    def create_session(
        self,
        agent_type: str,
        input_data: dict[str, Any],
        memory: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AgentSession:
        """Create a new execution session."""
        context = AgentContext(
            agent_type=agent_type,
            input_data=input_data,
            memory=memory or {},
            metadata=metadata or {},
        )
        session = AgentSession(context)
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[AgentSession]:
        """Retrieve an existing session."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[AgentSession]:
        """List all active sessions."""
        return list(self._sessions.values())

    def list_sessions_by_state(self, state: AgentState) -> list[AgentSession]:
        """List sessions filtered by state."""
        return [s for s in self._sessions.values() if s.state == state]

    def destroy_session(self, session_id: str) -> bool:
        """Remove a session from the runtime."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def clear(self) -> None:
        """Remove all sessions. Useful for testing."""
        self._sessions.clear()
