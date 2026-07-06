"""
Agent Communication layer for Milestone 3.

In-process messaging between agents:
- AgentMessage: envelope for a message
- AgentMessenger: routes messages between agents

No distributed networking. Single process only.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class AgentMessage:
    """A message sent between agents.

    Attributes:
        id: Unique message identifier
        sender: ID of the sending agent
        recipient: ID of the target agent ("*" for broadcast)
        message_type: Category of message (e.g., "delegate", "event", "response")
        payload: Message body
        timestamp: Unix timestamp
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: str = ""
    recipient: str = ""
    message_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


MessageHandler = Callable[[AgentMessage], None]


class AgentMessenger:
    """In-process message router for agent communication.

    Supports:
    - Direct messages (sender → recipient)
    - Broadcasts (sender → *)
    - Runtime events (system → listeners)
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[MessageHandler]] = {}
        self._history: list[AgentMessage] = []

    def register(self, agent_id: str, handler: MessageHandler) -> None:
        """Register a handler for messages addressed to an agent."""
        if agent_id not in self._handlers:
            self._handlers[agent_id] = []
        self._handlers[agent_id].append(handler)

    def unregister(self, agent_id: str, handler: MessageHandler) -> bool:
        """Remove a handler. Returns True if found and removed."""
        if agent_id not in self._handlers:
            return False
        try:
            self._handlers[agent_id].remove(handler)
            return True
        except ValueError:
            return False

    def send(self, message: AgentMessage) -> int:
        """Deliver a message to its recipient(s).

        Returns the number of handlers invoked.
        """
        self._history.append(message)
        count = 0

        if message.recipient == "*":
            # Broadcast to all registered agents except sender
            for agent_id, handlers in self._handlers.items():
                if agent_id != message.sender:
                    for handler in handlers:
                        try:
                            handler(message)
                            count += 1
                        except Exception:
                            # Isolated — one bad handler must not crash others
                            continue
        else:
            # Direct message
            for handler in self._handlers.get(message.recipient, []):
                try:
                    handler(message)
                    count += 1
                except Exception:
                    continue

        return count

    def delegate(
        self,
        sender: str,
        recipient: str,
        task: dict[str, Any],
    ) -> AgentMessage:
        """Convenience method to delegate a task to another agent.

        Returns the sent message.
        """
        message = AgentMessage(
            sender=sender,
            recipient=recipient,
            message_type="delegate",
            payload={"task": task},
        )
        self.send(message)
        return message

    def emit_event(self, event_type: str, payload: dict[str, Any]) -> AgentMessage:
        """Emit a runtime event to all listeners.

        Returns the sent message.
        """
        message = AgentMessage(
            sender="runtime",
            recipient="*",
            message_type=event_type,
            payload=payload,
        )
        self.send(message)
        return message

    def get_history(
        self,
        sender: Optional[str] = None,
        recipient: Optional[str] = None,
        message_type: Optional[str] = None,
    ) -> list[AgentMessage]:
        """Query message history with optional filters."""
        results = self._history
        if sender:
            results = [m for m in results if m.sender == sender]
        if recipient:
            results = [m for m in results if m.recipient == recipient]
        if message_type:
            results = [m for m in results if m.message_type == message_type]
        return results

    def clear_history(self) -> None:
        """Clear message history."""
        self._history.clear()
