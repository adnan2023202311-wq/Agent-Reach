"""
Tests for AgentMessenger and AgentMessage.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.agent_communication import AgentMessage, AgentMessenger


def test_message_defaults() -> None:
    """AgentMessage generates ID and timestamp by default."""
    msg = AgentMessage()
    assert msg.id
    assert msg.timestamp > 0


def test_message_fields() -> None:
    """AgentMessage stores all fields."""
    msg = AgentMessage(sender="a", recipient="b", message_type="test", payload={"x": 1})
    assert msg.sender == "a"
    assert msg.recipient == "b"
    assert msg.message_type == "test"
    assert msg.payload == {"x": 1}


def test_messenger_direct_message() -> None:
    """Messenger delivers direct messages."""
    messenger = AgentMessenger()
    received: list[AgentMessage] = []

    def handler(msg: AgentMessage) -> None:
        received.append(msg)

    messenger.register("agent-b", handler)
    msg = AgentMessage(sender="agent-a", recipient="agent-b", message_type="hello")
    count = messenger.send(msg)

    assert count == 1
    assert len(received) == 1
    assert received[0].sender == "agent-a"


def test_messenger_broadcast() -> None:
    """Messenger broadcasts to all agents except sender."""
    messenger = AgentMessenger()
    received_a: list[AgentMessage] = []
    received_b: list[AgentMessage] = []

    messenger.register("agent-a", lambda m: received_a.append(m))
    messenger.register("agent-b", lambda m: received_b.append(m))

    msg = AgentMessage(sender="agent-a", recipient="*", message_type="alert")
    count = messenger.send(msg)

    assert count == 1  # only agent-b receives (sender excluded)
    assert len(received_a) == 0
    assert len(received_b) == 1


def test_messenger_no_handler() -> None:
    """Sending to an agent with no handlers returns 0."""
    messenger = AgentMessenger()
    msg = AgentMessage(sender="a", recipient="nobody", message_type="test")
    assert messenger.send(msg) == 0


def test_messenger_unregister() -> None:
    """Unregister removes a handler."""
    messenger = AgentMessenger()

    def handler(msg: AgentMessage) -> None:
        pass

    messenger.register("agent-a", handler)
    assert messenger.unregister("agent-a", handler) is True
    assert messenger.send(AgentMessage(recipient="agent-a")) == 0


def test_messenger_unregister_missing() -> None:
    """Unregistering a non-existent handler returns False."""
    messenger = AgentMessenger()

    def handler(msg: AgentMessage) -> None:
        pass

    assert messenger.unregister("agent-a", handler) is False


def test_messenger_handler_exception_isolation() -> None:
    """A crashing handler does not affect other handlers."""
    messenger = AgentMessenger()
    received: list[AgentMessage] = []

    def bad_handler(msg: AgentMessage) -> None:
        raise RuntimeError("boom")

    def good_handler(msg: AgentMessage) -> None:
        received.append(msg)

    messenger.register("agent-x", bad_handler)
    messenger.register("agent-x", good_handler)

    count = messenger.send(AgentMessage(sender="a", recipient="agent-x"))
    assert count == 1
    assert len(received) == 1


def test_messenger_delegate() -> None:
    """Delegate creates and sends a task message."""
    messenger = AgentMessenger()
    received: list[AgentMessage] = []

    messenger.register("worker", lambda m: received.append(m))
    messenger.delegate("boss", "worker", {"action": "clean"})

    assert len(received) == 1
    assert received[0].message_type == "delegate"
    assert received[0].payload["task"]["action"] == "clean"


def test_messenger_emit_event() -> None:
    """Emit event broadcasts a runtime event."""
    messenger = AgentMessenger()
    received: list[AgentMessage] = []

    messenger.register("listener", lambda m: received.append(m))
    messenger.emit_event("session.started", {"session_id": "s1"})

    assert len(received) == 1
    assert received[0].sender == "runtime"
    assert received[0].message_type == "session.started"


def test_messenger_history() -> None:
    """Messenger records all sent messages."""
    messenger = AgentMessenger()
    messenger.send(AgentMessage(sender="a", recipient="b", message_type="t1"))
    messenger.send(AgentMessage(sender="a", recipient="c", message_type="t2"))

    assert len(messenger.get_history()) == 2
    assert len(messenger.get_history(sender="a")) == 2
    assert len(messenger.get_history(recipient="b")) == 1
    assert len(messenger.get_history(message_type="t2")) == 1


def test_messenger_clear_history() -> None:
    """Clear history removes all records."""
    messenger = AgentMessenger()
    messenger.send(AgentMessage())
    messenger.clear_history()
    assert len(messenger.get_history()) == 0
