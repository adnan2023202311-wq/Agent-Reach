"""
Knowledge Layer for Milestone 4.

Inspired by Zep's knowledge indexing & retrieval concepts, but built
natively without external service coupling.

Provides:
- KnowledgeEntry: a unit of knowledge with content, source, and tags
- KnowledgeLayer: CRUD and search over an in-memory knowledge index

Per ADR-003: Memory, Knowledge, and Skills are independent subsystems.
This module MUST NOT depend on the Memory Layer.

Layer: Application/Core — depends inward on domain/ and infrastructure/ only.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class KnowledgeEntry:
    """A single unit of knowledge."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    source: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.perf_counter)
    metadata: dict[str, Any] = field(default_factory=dict)


class KnowledgeLayer:
    """In-memory knowledge indexing and retrieval.

    Stores KnowledgeEntry objects and provides search by:
    - Full-text substring matching (simple but native)
    - Tag filtering
    - Source filtering
    """

    def __init__(self) -> None:
        self._entries: dict[str, KnowledgeEntry] = {}

    def add(self, entry: KnowledgeEntry) -> str:
        """Add a knowledge entry and return its ID."""
        self._entries[entry.id] = entry
        return entry.id

    def add_text(
        self,
        content: str,
        source: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Convenience method to create and add an entry from text."""
        entry = KnowledgeEntry(
            content=content,
            source=source,
            tags=tags or [],
            metadata=metadata or {},
        )
        return self.add(entry)

    def get(self, entry_id: str) -> Optional[KnowledgeEntry]:
        """Retrieve an entry by ID."""
        return self._entries.get(entry_id)

    def remove(self, entry_id: str) -> bool:
        """Remove an entry by ID."""
        if entry_id in self._entries:
            del self._entries[entry_id]
            return True
        return False

    def search(self, query: str) -> list[KnowledgeEntry]:
        """Full-text search by substring (case-insensitive)."""
        query_lower = query.lower()
        return [
            e for e in self._entries.values()
            if query_lower in e.content.lower()
        ]

    def search_by_tag(self, tag: str) -> list[KnowledgeEntry]:
        """Find entries that have a specific tag."""
        return [e for e in self._entries.values() if tag in e.tags]

    def search_by_source(self, source: str) -> list[KnowledgeEntry]:
        """Find entries from a specific source."""
        return [e for e in self._entries.values() if e.source == source]

    def list_all(self) -> list[KnowledgeEntry]:
        """List all knowledge entries."""
        return list(self._entries.values())

    def count(self) -> int:
        """Return the total number of entries."""
        return len(self._entries)

    def clear(self) -> None:
        """Remove all entries. Useful for testing."""
        self._entries.clear()
