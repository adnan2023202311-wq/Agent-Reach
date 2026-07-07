"""
Memory Layer for Milestone 4.

Inspired by LongCat's long-context memory architecture and Mem0's
memory lifecycle concepts, but built natively without library
dependencies.

Provides:
- MemoryItem: a unit of memory with importance, recency, and type
- MemoryType: short_term, long_term, archived
- MemoryLayer: lifecycle management, context windowing, and retrieval

Per ADR-003: Memory, Knowledge, and Skills are independent subsystems.
This module MUST NOT depend on the Knowledge Layer.

Layer: Application/Core — depends inward on domain/ and infrastructure/ only.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class MemoryType(str, Enum):
    """Lifecycle stage of a memory item."""

    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    ARCHIVED = "archived"


@dataclass
class MemoryItem:
    """A single unit of memory."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: Any = None
    memory_type: MemoryType = MemoryType.SHORT_TERM
    importance: float = 0.5  # 0.0 to 1.0
    created_at: float = field(default_factory=time.perf_counter)
    last_accessed: float = field(default_factory=time.perf_counter)
    access_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        """Update last_accessed and increment access_count."""
        self.last_accessed = time.perf_counter()
        self.access_count += 1

    def score(self) -> float:
        """Compute a relevance score based on importance and recency.

        Higher is more relevant.
        """
        age = time.perf_counter() - self.last_accessed
        recency = 1.0 / (1.0 + age)
        return self.importance * 0.6 + recency * 0.4


class MemoryLayer:
    """In-memory memory management with lifecycle and context windows.

    Memories start as SHORT_TERM. Important or frequently accessed
    memories can be promoted to LONG_TERM. Old or unimportant memories
    can be archived or pruned.
    """

    def __init__(self, max_short_term: int = 100, max_long_term: int = 500) -> None:
        self._memories: dict[str, MemoryItem] = {}
        self._max_short_term = max_short_term
        self._max_long_term = max_long_term

    def store(
        self,
        content: Any,
        importance: float = 0.5,
        memory_type: MemoryType = MemoryType.SHORT_TERM,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a new memory and return its ID."""
        item = MemoryItem(
            content=content,
            memory_type=memory_type,
            importance=importance,
            metadata=metadata or {},
        )
        self._memories[item.id] = item
        self._enforce_limits()
        return item.id

    def get(self, memory_id: str) -> Optional[MemoryItem]:
        """Retrieve a memory by ID and update its access stats."""
        item = self._memories.get(memory_id)
        if item is not None:
            item.touch()
        return item

    def retrieve_relevant(self, count: int = 10) -> list[MemoryItem]:
        """Retrieve the most relevant memories by score."""
        sorted_items = sorted(
            self._memories.values(),
            key=lambda m: m.score(),
            reverse=True,
        )
        for item in sorted_items[:count]:
            item.touch()
        return sorted_items[:count]

    def retrieve_by_type(self, memory_type: MemoryType) -> list[MemoryItem]:
        """Retrieve all memories of a given type."""
        return [m for m in self._memories.values() if m.memory_type == memory_type]

    def promote(self, memory_id: str) -> bool:
        """Promote a memory to long_term."""
        item = self._memories.get(memory_id)
        if item is None:
            return False
        item.memory_type = MemoryType.LONG_TERM
        item.touch()
        self._enforce_limits()
        return True

    def archive(self, memory_id: str) -> bool:
        """Archive a memory."""
        item = self._memories.get(memory_id)
        if item is None:
            return False
        item.memory_type = MemoryType.ARCHIVED
        return True

    def prune(self, max_age_seconds: float = 3600.0) -> int:
        """Remove old short_term memories that haven't been accessed.

        Returns the number of items removed.
        """
        now = time.perf_counter()
        to_remove = [
            mid for mid, item in self._memories.items()
            if item.memory_type == MemoryType.SHORT_TERM
            and (now - item.last_accessed) > max_age_seconds
        ]
        for mid in to_remove:
            del self._memories[mid]
        return len(to_remove)

    def consolidate(self, threshold: float = 0.7) -> int:
        """Promote frequently accessed short_term memories to long_term.

        Returns the number of items promoted.
        """
        promoted = 0
        for item in list(self._memories.values()):
            if item.memory_type == MemoryType.SHORT_TERM and item.score() >= threshold:
                item.memory_type = MemoryType.LONG_TERM
                promoted += 1
        self._enforce_limits()
        return promoted

    def _enforce_limits(self) -> None:
        """Ensure memory counts stay within configured limits."""
        short_term = [m for m in self._memories.values() if m.memory_type == MemoryType.SHORT_TERM]
        if len(short_term) > self._max_short_term:
            sorted_st = sorted(short_term, key=lambda m: m.score())
            for item in sorted_st[: len(short_term) - self._max_short_term]:
                item.memory_type = MemoryType.ARCHIVED

        long_term = [m for m in self._memories.values() if m.memory_type == MemoryType.LONG_TERM]
        if len(long_term) > self._max_long_term:
            sorted_lt = sorted(long_term, key=lambda m: m.score())
            for item in sorted_lt[: len(long_term) - self._max_long_term]:
                item.memory_type = MemoryType.ARCHIVED

    def count(self) -> int:
        """Return total number of memories."""
        return len(self._memories)

    def clear(self) -> None:
        """Remove all memories. Useful for testing."""
        self._memories.clear()
