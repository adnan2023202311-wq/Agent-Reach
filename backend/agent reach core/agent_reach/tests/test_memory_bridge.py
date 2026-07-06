"""
Tests for MemoryBridge.

Covers read/write, conversation history, and execution history.
"""

from __future__ import annotations

import pytest

from core.memory_bridge import MemoryBridge
from infrastructure.memory_store import InMemoryStore


async def test_read_write() -> None:
    """Basic read/write round-trip."""
    bridge = MemoryBridge()
    await bridge.write("sess-1", "key", "value")
    assert await bridge.read("sess-1", "key") == "value"


async def test_read_missing_key() -> None:
    """Reading a missing key returns None."""
    bridge = MemoryBridge()
    assert await bridge.read("sess-1", "missing") is None


async def test_conversation_history() -> None:
    """Conversation history starts empty and accumulates."""
    bridge = MemoryBridge()
    assert await bridge.read_conversation("sess-1") == []

    await bridge.append_conversation("sess-1", "user", "hello")
    await bridge.append_conversation("sess-1", "assistant", "hi")

    history = await bridge.read_conversation("sess-1")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


async def test_execution_history() -> None:
    """Execution history starts empty and accumulates."""
    bridge = MemoryBridge()
    assert await bridge.read_execution_history("sess-1") == []

    await bridge.append_execution("sess-1", "task-a", "ok", True)
    await bridge.append_execution("sess-1", "task-b", "fail", False)

    history = await bridge.read_execution_history("sess-1")
    assert len(history) == 2
    assert history[0]["task"] == "task-a"
    assert history[0]["success"] is True
    assert history[1]["success"] is False


async def test_clear_session() -> None:
    """Clearing a session wipes its history."""
    bridge = MemoryBridge()
    await bridge.append_conversation("sess-1", "user", "hello")
    await bridge.append_execution("sess-1", "task", "ok", True)

    await bridge.clear_session("sess-1")
    assert await bridge.read_conversation("sess-1") == []
    assert await bridge.read_execution_history("sess-1") == []


async def test_session_isolation() -> None:
    """Different sessions do not share data."""
    bridge = MemoryBridge()
    await bridge.write("sess-a", "key", "a")
    await bridge.write("sess-b", "key", "b")
    assert await bridge.read("sess-a", "key") == "a"
    assert await bridge.read("sess-b", "key") == "b"


async def test_uses_provided_store() -> None:
    """MemoryBridge can be constructed with an existing store."""
    store = InMemoryStore()
    bridge = MemoryBridge(store)
    await bridge.write("sess-1", "key", "value")
    assert await store.load("sess-1", "key") == "value"
