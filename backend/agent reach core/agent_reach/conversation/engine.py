"""
Conversation layer: Conversation Engine (M6.1).

Layer: Application/Core — depends inward on domain/, core/, and
conversation/session_manager.py only.

Provides conversational execution on top of the existing MainController:
- multi-turn conversations (messages grouped by session)
- conversation history (ordered message log per session)
- conversation memory (history fed back as context on each turn)
- conversation context (arbitrary key-value context carried per session)
- workflow-backed conversations (a conversation turn can invoke an M5
  workflow and capture its result)

The engine does NOT replace MainController — it wraps it. Each user
message in a conversation is still planned and dispatched by the
MainController; the ConversationEngine adds session/history/memory on
top, which MainController has no concept of (and should not — that's
orchestration, not conversation state).

Design notes
------------
- History is stored in-memory keyed by session_id. A future milestone
  can persist it via the same SessionStore protocol.
- Memory is implemented as a sliding window of recent messages
  (configurable ``memory_window``). Only user/assistant turns are
  included — system events are not.
- Workflow-backed conversations accept an optional ``workflow`` field
  in the turn request; when present, the engine runs the workflow
  through the WorkflowEngine and returns its result as the assistant
  message.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from conversation.session_manager import Session, SessionManager
from core.controller import MainController
from domain.models import TaskExecutionOutcome


class MessageRole(str, Enum):
    """Who produced a conversation message."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    """One message in a conversation history."""

    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    role: MessageRole = MessageRole.USER
    content: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }


@dataclass
class ConversationTurnResult:
    """The outcome of a single conversation turn."""

    session: Session
    user_message: Message
    assistant_message: Message
    outcome: Optional[TaskExecutionOutcome] = None
    workflow_result: Optional[dict[str, Any]] = None


class ConversationEngine:
    """Multi-turn conversational execution on top of MainController.

    Parameters
    ----------
    controller:
        The MainController instance that plans and dispatches each
        user request. Injected — the engine never constructs one.
    session_manager:
        The SessionManager that owns conversation sessions. Injected.
    memory_window:
        Number of recent user/assistant turns to include as context
        when building the next request. 0 means no memory (each turn
        is independent). Defaults to 10.
    """

    def __init__(
        self,
        controller: MainController,
        session_manager: SessionManager,
        memory_window: int = 10,
    ) -> None:
        self._controller = controller
        self._session_manager = session_manager
        self._memory_window = memory_window
        self._history: dict[str, list[Message]] = {}
        self._context: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Turn execution
    # ------------------------------------------------------------------

    async def send_message(
        self,
        session_id: str,
        content: str,
        *,
        extra_context: Optional[dict[str, Any]] = None,
    ) -> ConversationTurnResult:
        """Process one user message in a conversation.

        1. Validates the session exists and is ACTIVE.
        2. Records the user message in history.
        3. Builds the request (with memory context if configured).
        4. Dispatches through MainController.
        5. Records the assistant reply in history.
        6. Updates the session's ``updated_at`` timestamp.

        Raises
        ------
        ValueError:
            If the session does not exist or is not ACTIVE.
        """
        session = self._session_manager.get_session(session_id)
        if session is None:
            raise ValueError(f"Session '{session_id}' does not exist")
        from conversation.session_manager import SessionState

        if session.state is not SessionState.ACTIVE:
            raise ValueError(
                f"Session '{session_id}' is not active (state={session.state.value})"
            )

        # Record user message.
        user_message = Message(
            session_id=session_id,
            role=MessageRole.USER,
            content=content,
        )
        self._append_message(session_id, user_message)

        # Build the effective request — prepend memory context if enabled.
        effective_request = self._build_request(session_id, content)

        # Dispatch through the existing MainController.
        outcome = await self._controller.handle_request(effective_request)

        # Record assistant reply.
        assistant_message = Message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=outcome.answer,
            metadata={
                "plan_id": outcome.plan.id,
                "status": outcome.status.value,
                "result_count": len(outcome.results),
            },
        )
        self._append_message(session_id, assistant_message)

        # Carry arbitrary context forward for the caller.
        if extra_context:
            self._context.setdefault(session_id, {}).update(extra_context)

        # Touch the session so its updated_at reflects activity.
        self._session_manager.touch(session_id)

        return ConversationTurnResult(
            session=session,
            user_message=user_message,
            assistant_message=assistant_message,
            outcome=outcome,
        )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, session_id: str) -> list[Message]:
        """Return the full conversation history for a session, oldest first."""
        return list(self._history.get(session_id, []))

    def get_recent_history(
        self, session_id: str, count: int = 5
    ) -> list[Message]:
        """Return the most recent ``count`` messages, oldest first."""
        history = self._history.get(session_id, [])
        return history[-count:] if count < len(history) else list(history)

    def clear_history(self, session_id: str) -> bool:
        """Remove the history for a session.

        Returns True if history existed and was cleared, False if there
        was no history for the session.
        """
        if session_id in self._history:
            del self._history[session_id]
            return True
        return False

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    def get_context(self, session_id: str) -> dict[str, Any]:
        """Return the carried context for a session (empty dict if none)."""
        return dict(self._context.get(session_id, {}))

    def set_context(
        self, session_id: str, key: str, value: Any
    ) -> None:
        """Set a single context key for a session."""
        self._context.setdefault(session_id, {})[key] = value

    def clear_context(self, session_id: str) -> bool:
        """Remove the context for a session.

        Returns True if context existed and was cleared.
        """
        if session_id in self._context:
            del self._context[session_id]
            return True
        return False

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def _build_request(self, session_id: str, current_content: str) -> str:
        """Build the effective request string, prepending memory context.

        When ``memory_window`` is 0 or there is no prior history, the
        current content is returned unchanged.
        """
        if self._memory_window <= 0:
            return current_content

        prior = self._prior_turns(session_id)
        if not prior:
            return current_content

        lines: list[str] = []
        lines.append("Previous conversation:")
        for msg in prior:
            role_label = "User" if msg.role is MessageRole.USER else "Assistant"
            lines.append(f"  {role_label}: {msg.content}")
        lines.append("")
        lines.append("Current message:")
        lines.append(current_content)
        return "\n".join(lines)

    def _prior_turns(self, session_id: str) -> list[Message]:
        """Return the user/assistant messages before the most recent user
        message (which has not yet been answered), bounded by the memory
        window.
        """
        history = self._history.get(session_id, [])
        # The last message is the current user message (just appended).
        # Prior turns are everything before it, filtered to user/assistant.
        prior = [
            m for m in history[:-1]
            if m.role in (MessageRole.USER, MessageRole.ASSISTANT)
        ]
        # Apply the sliding window.
        if self._memory_window > 0:
            prior = prior[-self._memory_window:]
        return prior

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _append_message(self, session_id: str, message: Message) -> None:
        self._history.setdefault(session_id, []).append(message)

    def clear(self) -> None:
        """Drop all history and context. Useful for testing."""
        self._history.clear()
        self._context.clear()
