"""
Conversation layer: Session Manager (M6.2).

Layer: Application/Core — depends inward on domain/ only.

Manages the lifecycle of conversation sessions:
- create session
- resume session
- terminate session
- session persistence (in-memory + JSON)
- session isolation

Reuses the existing AgentRuntime session patterns from core/runtime.py
but is distinct from it: AgentRuntime manages agent *execution*
sessions (one per agent run), while SessionManager manages
*conversation* sessions (multi-turn user conversations that may
invoke many agent runs).

Design notes
------------
- Sessions are isolated by session_id (UUID).
- Persistence is pluggable: InMemorySessionStore (default) and
  JsonSessionStore (file-backed). The store is injected so tests
  can use the in-memory variant without touching the filesystem.
- The manager is synchronous at the data layer (no I/O in the hot
  path) — persistence writes are fire-and-forget best-effort, same
  convention as WorkflowPersistence.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol


class SessionState(str, Enum):
    """Finite state machine for a conversation session."""

    ACTIVE = "active"
    PAUSED = "paused"
    TERMINATED = "terminated"


@dataclass
class Session:
    """One conversation session.

    A session groups multiple conversation turns (messages) under a
    stable identifier so a client can resume a prior conversation.
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    state: SessionState = SessionState.ACTIVE
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        """Deserialize from a dict. Raises ``ValueError`` on invalid input."""
        if not isinstance(data, dict):
            raise ValueError(f"Session must be a dict, got {type(data).__name__}")
        try:
            state = SessionState(data.get("state", SessionState.ACTIVE.value))
        except ValueError as exc:
            raise ValueError(f"Unknown SessionState: {data.get('state')!r}") from exc
        return cls(
            session_id=str(data["session_id"]),
            user_id=str(data.get("user_id", "")),
            state=state,
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            metadata=dict(data.get("metadata", {})),
        )


# ---------------------------------------------------------------------------
# Persistence stores
# ---------------------------------------------------------------------------


class SessionStore(Protocol):
    """Persistence contract for conversation sessions.

    A store is the single source of truth for persisted sessions.
    The SessionManager delegates load/save/delete to it.
    """

    def save(self, session: Session) -> None: ...
    def load(self, session_id: str) -> Optional[Session]: ...
    def delete(self, session_id: str) -> bool: ...
    def list_all(self) -> list[Session]: ...
    def clear(self) -> None: ...


class InMemorySessionStore:
    """In-memory session store — default for single-process deployments."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def save(self, session: Session) -> None:
        self._sessions[session.session_id] = session

    def load(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def list_all(self) -> list[Session]:
        return list(self._sessions.values())

    def clear(self) -> None:
        self._sessions.clear()


# ---------------------------------------------------------------------------
# Session Manager
# ---------------------------------------------------------------------------


class SessionManager:
    """Create, resume, terminate, and query conversation sessions.

    Parameters
    ----------
    store:
        Persistence backend. Defaults to InMemorySessionStore.
    """

    def __init__(self, store: Optional[SessionStore] = None) -> None:
        self._store: SessionStore = store or InMemorySessionStore()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create_session(
        self,
        user_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> Session:
        """Create a new conversation session.

        The session is created in ACTIVE state and persisted immediately.
        """
        now = time.time()
        session = Session(
            user_id=user_id,
            state=SessionState.ACTIVE,
            created_at=now,
            updated_at=now,
            metadata=dict(metadata or {}),
        )
        self._store.save(session)
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Return the session with the given ID, or None."""
        return self._store.load(session_id)

    def resume_session(self, session_id: str) -> Optional[Session]:
        """Resume a paused session.

        Returns the session in ACTIVE state, or None if the session
        does not exist or is TERMINATED (terminated sessions cannot
        be resumed — create a new one instead).
        """
        session = self._store.load(session_id)
        if session is None:
            return None
        if session.state is SessionState.TERMINATED:
            return None
        session.state = SessionState.ACTIVE
        session.updated_at = time.time()
        self._store.save(session)
        return session

    def pause_session(self, session_id: str) -> bool:
        """Pause an active session.

        Returns True if the session was paused, False if it does not
        exist or is not ACTIVE.
        """
        session = self._store.load(session_id)
        if session is None or session.state is not SessionState.ACTIVE:
            return False
        session.state = SessionState.PAUSED
        session.updated_at = time.time()
        self._store.save(session)
        return True

    def terminate_session(self, session_id: str) -> bool:
        """Terminate a session.

        Terminated sessions cannot be resumed. Returns True if the
        session was terminated, False if it does not exist.
        """
        session = self._store.load(session_id)
        if session is None:
            return False
        session.state = SessionState.TERMINATED
        session.updated_at = time.time()
        self._store.save(session)
        return True

    def delete_session(self, session_id: str) -> bool:
        """Permanently delete a session.

        Returns True if a session was deleted, False if it did not exist.
        """
        return self._store.delete(session_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_sessions(self, user_id: str = "") -> list[Session]:
        """List sessions, optionally filtered by user_id."""
        sessions = self._store.list_all()
        if user_id:
            sessions = [s for s in sessions if s.user_id == user_id]
        return sessions

    def list_sessions_by_state(self, state: SessionState) -> list[Session]:
        """List sessions filtered by state."""
        return [s for s in self._store.list_all() if s.state is state]

    def touch(self, session_id: str) -> bool:
        """Update the session's ``updated_at`` timestamp.

        Returns True if the session exists, False otherwise.
        """
        session = self._store.load(session_id)
        if session is None:
            return False
        session.updated_at = time.time()
        self._store.save(session)
        return True

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Remove every session. Useful for testing."""
        self._store.clear()
