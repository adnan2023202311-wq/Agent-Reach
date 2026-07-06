"""
Memory Bridge for Milestone 3.

Connects the Agent Runtime with the existing InMemoryStore.
Provides runtime-friendly accessors for:
- read / write memory
- conversation history
- execution history

Does NOT redesign InMemoryStore — it is wrapped, not replaced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from infrastructure.memory_store import InMemoryStore


@dataclass
class MemoryEntry:
    """A single memory entry with metadata."""

    key: str
    value: Any
    timestamp: str = ""
    entry_type: str = "generic"  # generic | conversation | execution


class MemoryBridge:
    """Bridge between Agent Runtime and InMemoryStore.

    Keys are namespaced by session_id to avoid collisions.
    """

    def __init__(self, store: Optional[InMemoryStore] = None) -> None:
        self._store = store or InMemoryStore()

    async def read(self, session_id: str, key: str) -> Optional[Any]:
        """Read a value from memory."""
        return await self._store.load(session_id, key)

    async def write(self, session_id: str, key: str, value: Any) -> None:
        """Write a value to memory."""
        await self._store.save(session_id, key, value)

    async def read_conversation(self, session_id: str) -> list[dict[str, Any]]:
        """Read conversation history for a session."""
        history = await self._store.load(session_id, "conversation")
        if history is None:
            return []
        return history if isinstance(history, list) else [history]

    async def append_conversation(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        """Append a message to the conversation history."""
        history = await self.read_conversation(session_id)
        history.append({"role": role, "content": content, "timestamp": __import__("datetime").datetime.utcnow().isoformat()})
        await self._store.save(session_id, "conversation", history)

    async def read_execution_history(self, session_id: str) -> list[dict[str, Any]]:
        """Read execution history for a session."""
        history = await self._store.load(session_id, "execution_history")
        if history is None:
            return []
        return history if isinstance(history, list) else [history]

    async def append_execution(
        self,
        session_id: str,
        task: str,
        result: Any,
        success: bool,
    ) -> None:
        """Append an execution record."""
        history = await self.read_execution_history(session_id)
        history.append(
            {
                "task": task,
                "result": result,
                "success": success,
                "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
            }
        )
        await self._store.save(session_id, "execution_history", history)

    async def clear_session(self, session_id: str) -> None:
        """Clear all memory for a session."""
        await self._store.save(session_id, "conversation", [])
        await self._store.save(session_id, "execution_history", [])
