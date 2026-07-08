"""
LongCat Memory Engine (M7.1).

An advanced hierarchical memory system inspired by LongCat's long-context
memory architecture. Extends the existing MemoryLayer with:

- Short-Term Memory (existing, enhanced)
- Working Memory (active context window)
- Long-Term Memory (existing, enhanced)
- Compressed Memory (summarized/compressed storage)
- Context Compression & Expansion
- Semantic Memory Search
- Memory Ranking & Importance Scoring
- Memory Versioning & Snapshots
- Memory Replay & Consolidation
- Memory Graph Integration

Layer: Application/Core — depends inward on domain/ and infrastructure/ only.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from memory.layer import MemoryItem, MemoryLayer, MemoryType


# ---------------------------------------------------------------------------
# New Types
# ---------------------------------------------------------------------------

class CompressedMemoryType(str, Enum):
    """Type of compressed memory."""
    CONVERSATION = "conversation"
    PROJECT = "project"
    KNOWLEDGE = "knowledge"
    EXECUTION = "execution"


@dataclass
class MemorySnapshot:
    """A point-in-time snapshot of the memory system."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 1
    timestamp: float = field(default_factory=time.time)
    label: str = ""
    memory_ids: list[str] = field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "timestamp": self.timestamp,
            "label": self.label,
            "memory_ids": list(self.memory_ids),
            "summary": self.summary,
            "metadata": dict(self.metadata),
        }


@dataclass
class CompressedMemory:
    """A compressed representation of a group of related memories."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    compression_type: CompressedMemoryType = CompressedMemoryType.CONVERSATION
    source_ids: list[str] = field(default_factory=list)
    content: str = ""
    summary: str = ""
    importance: float = 0.5
    created_at: float = field(default_factory=time.time)
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "compression_type": self.compression_type.value,
            "source_ids": list(self.source_ids),
            "content": self.content,
            "summary": self.summary,
            "importance": self.importance,
            "created_at": self.created_at,
            "version": self.version,
            "metadata": dict(self.metadata),
        }


@dataclass
class MemoryGraphNode:
    """A node in the memory graph linking memories."""

    memory_id: str
    edges: dict[str, str] = field(default_factory=dict)
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Retrieval & Ranking
# ---------------------------------------------------------------------------


class MemoryRanker:
    """Scores and ranks memories by importance, recency, and relevance."""

    def __init__(
        self,
        importance_weight: float = 0.4,
        recency_weight: float = 0.3,
        access_weight: float = 0.2,
        relevance_weight: float = 0.1,
    ) -> None:
        self._importance_weight = importance_weight
        self._recency_weight = recency_weight
        self._access_weight = access_weight
        self._relevance_weight = relevance_weight

    def score(
        self,
        memory: MemoryItem,
        *,
        query: str = "",
        now: Optional[float] = None,
    ) -> float:
        """Compute a composite relevance score."""
        now = now or time.time()

        importance_score = memory.importance

        age = now - memory.last_accessed
        recency_score = 1.0 / (1.0 + age / 3600.0)

        access_score = min(1.0, memory.access_count / 100.0)

        relevance_score = 0.0
        if query:
            content_str = str(memory.content or "").lower()
            query_lower = query.lower()
            if query_lower in content_str:
                relevance_score = 0.5 + 0.5 * (len(query_lower) / max(1, len(content_str)))

        return (
            self._importance_weight * importance_score
            + self._recency_weight * recency_score
            + self._access_weight * access_score
            + self._relevance_weight * relevance_score
        )

    def rank(
        self,
        memories: list[MemoryItem],
        *,
        query: str = "",
        limit: int = 10,
    ) -> list[MemoryItem]:
        """Rank memories by composite score, returning top ``limit``."""
        now = time.time()
        scored = [(m, self.score(m, query=query, now=now)) for m in memories]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [m for m, _ in scored[:limit]]


# ---------------------------------------------------------------------------
# Semantic Search
# ---------------------------------------------------------------------------


class SemanticMemorySearch:
    """Semantic search over memory content using Jaccard similarity."""

    def __init__(self) -> None:
        self._inverted_index: dict[str, set[str]] = {}

    def index(self, memory_id: str, content: str) -> None:
        """Index a memory's content for search."""
        tokens = self._tokenize(content)
        for token in tokens:
            self._inverted_index.setdefault(token, set()).add(memory_id)

    def deindex(self, memory_id: str) -> None:
        """Remove a memory from the index."""
        for token_set in self._inverted_index.values():
            token_set.discard(memory_id)

    def search(
        self,
        query: str,
        candidate_ids: Optional[set[str]] = None,
        limit: int = 10,
    ) -> list[tuple[str, float]]:
        """Search for memories semantically similar to the query."""
        query_tokens = set(self._tokenize(query))
        if not query_tokens:
            return []

        scores: dict[str, float] = {}
        for token in query_tokens:
            matching = self._inverted_index.get(token, set())
            for mid in matching:
                if candidate_ids is not None and mid not in candidate_ids:
                    continue
                scores[mid] = scores.get(mid, 0.0) + 1.0

        for mid in list(scores.keys()):
            memory_tokens = set()
            for t, ids in self._inverted_index.items():
                if mid in ids:
                    memory_tokens.add(t)
            if memory_tokens:
                scores[mid] = scores[mid] / len(query_tokens | memory_tokens)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:limit]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple tokenization: lowercase, match sequences of 2+ word chars."""
        import re

        return re.findall(r"\w{2,}", text.lower())

    def clear(self) -> None:
        """Clear the search index."""
        self._inverted_index.clear()


# ---------------------------------------------------------------------------
# LongCat Memory Engine
# ---------------------------------------------------------------------------


class LongCatMemoryEngine:
    """Advanced hierarchical memory engine."""

    def __init__(
        self,
        working_memory_size: int = 50,
        max_short_term: int = 200,
        max_long_term: int = 1000,
        max_compressed: int = 500,
    ) -> None:
        self._layer = MemoryLayer(
            max_short_term=max_short_term,
            max_long_term=max_long_term,
        )
        self._working_memory: list[str] = []
        self._working_memory_size = working_memory_size
        self._compressed: dict[str, CompressedMemory] = {}
        self._max_compressed = max_compressed
        self._snapshots: dict[str, MemorySnapshot] = {}
        self._snapshot_versions: dict[str, int] = {}
        self._graph: dict[str, MemoryGraphNode] = {}
        self._ranker = MemoryRanker()
        self._search = SemanticMemorySearch()
        self._consolidation_count: int = 0
        self._pinned: set[str] = set()

    # ------------------------------------------------------------------
    # Core memory operations
    # ------------------------------------------------------------------

    def store(
        self,
        content: Any,
        importance: float = 0.5,
        memory_type: MemoryType = MemoryType.SHORT_TERM,
        metadata: dict[str, Any] | None = None,
        add_to_working: bool = True,
    ) -> str:
        """Store a memory and optionally add to working memory."""
        memory_id = self._layer.store(
            content=content,
            importance=importance,
            memory_type=memory_type,
            metadata=metadata or {},
        )
        if add_to_working:
            self._add_to_working(memory_id)
        self._search.index(memory_id, str(content))
        return memory_id

    def get(self, memory_id: str) -> Optional[MemoryItem]:
        """Retrieve a memory by ID."""
        memory = self._layer.get(memory_id)
        if memory is not None:
            self._add_to_working(memory_id)
        return memory

    def retrieve_relevant(
        self,
        count: int = 10,
        query: str = "",
    ) -> list[MemoryItem]:
        """Retrieve most relevant memories using the ranker."""
        all_memories = list(self._layer._memories.values())
        active = [m for m in all_memories if m.memory_type != MemoryType.ARCHIVED]
        return self._ranker.rank(active, query=query, limit=count)

    def semantic_search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[tuple[MemoryItem, float]]:
        """Semantic search across memories."""
        results = self._search.search(query, limit=limit)
        items: list[tuple[MemoryItem, float]] = []
        for mid, score in results:
            mem = self._layer.get(mid)
            if mem is not None:
                items.append((mem, score))
        return items

    # ------------------------------------------------------------------
    # Browse / Delete / Pin / Merge (M9.7)
    # ------------------------------------------------------------------

    def browse(
        self,
        memory_type: Optional[MemoryType] = None,
        offset: int = 0,
        limit: int = 50,
        pinned_only: bool = False,
    ) -> list[MemoryItem]:
        """Browse stored memories with pagination.

        Ordered newest-first by creation time. Unlike retrieve_relevant
        this does not touch() items — browsing the memory studio must
        not distort access-based relevance scores.
        """
        items = list(self._layer._memories.values())
        if memory_type is not None:
            items = [m for m in items if m.memory_type == memory_type]
        if pinned_only:
            items = [m for m in items if m.id in self._pinned]
        items.sort(key=lambda m: m.created_at, reverse=True)
        offset = max(0, offset)
        limit = max(0, limit)
        return items[offset : offset + limit]

    def delete(self, memory_id: str) -> bool:
        """Permanently delete a memory.

        Removes it from the layer, the search index, working memory,
        the memory graph, and the pinned set. Returns False if the id
        is unknown.
        """
        if memory_id not in self._layer._memories:
            return False
        del self._layer._memories[memory_id]
        self._search.deindex(memory_id)
        if memory_id in self._working_memory:
            self._working_memory.remove(memory_id)
        self._pinned.discard(memory_id)
        self._layer.protected_ids.discard(memory_id)
        # Remove the graph node and any edges pointing at it.
        self._graph.pop(memory_id, None)
        for node in self._graph.values():
            node.edges = {
                target: rel
                for target, rel in node.edges.items()
                if target != memory_id
            }
        return True

    def pin(self, memory_id: str) -> bool:
        """Pin a memory: exempt from pruning and limit-archiving."""
        if memory_id not in self._layer._memories:
            return False
        self._pinned.add(memory_id)
        self._layer.protected_ids.add(memory_id)
        return True

    def unpin(self, memory_id: str) -> bool:
        """Remove a pin. Returns False if the memory wasn't pinned."""
        if memory_id not in self._pinned:
            return False
        self._pinned.discard(memory_id)
        self._layer.protected_ids.discard(memory_id)
        return True

    def is_pinned(self, memory_id: str) -> bool:
        return memory_id in self._pinned

    @property
    def pinned_ids(self) -> set[str]:
        return set(self._pinned)

    def merge(self, memory_ids: list[str], separator: str = "\n") -> Optional[str]:
        """Merge several memories into one and delete the sources.

        The merged memory keeps the maximum importance of the sources,
        combines their metadata (later sources win key conflicts), and
        is pinned if any source was pinned. Returns the new memory id,
        or None when fewer than two of the ids exist.
        """
        sources = [
            self._layer._memories[mid]
            for mid in memory_ids
            if mid in self._layer._memories
        ]
        if len(sources) < 2:
            return None

        content = separator.join(str(m.content) for m in sources)
        importance = max(m.importance for m in sources)
        metadata: dict[str, Any] = {}
        for m in sources:
            metadata.update(m.metadata)
        metadata["merged_from"] = [m.id for m in sources]
        any_pinned = any(m.id in self._pinned for m in sources)

        merged_id = self.store(
            content=content,
            importance=importance,
            metadata=metadata,
            add_to_working=False,
        )
        for m in sources:
            self.delete(m.id)
        if any_pinned:
            self.pin(merged_id)
        return merged_id

    # ------------------------------------------------------------------
    # Working memory
    # ------------------------------------------------------------------

    @property
    def working_memory(self) -> list[MemoryItem]:
        """Current working memory items."""
        items: list[MemoryItem] = []
        for mid in self._working_memory:
            mem = self._layer._memories.get(mid)
            if mem is not None:
                items.append(mem)
        return items

    def get_working_context(self, max_items: int = 10) -> list[Any]:
        """Get working memory contents as a context list."""
        items = self.working_memory[:max_items]
        return [m.content for m in items]

    def clear_working_memory(self) -> None:
        """Clear working memory without deleting underlying memories."""
        self._working_memory.clear()

    def set_working_memory(self, memory_ids: list[str]) -> None:
        """Explicitly set working memory to specific memory IDs."""
        self._working_memory = [
            mid for mid in memory_ids if mid in self._layer._memories
        ]

    def _add_to_working(self, memory_id: str) -> None:
        """Add a memory to working memory, maintaining size limit."""
        if memory_id in self._working_memory:
            self._working_memory.remove(memory_id)
        self._working_memory.insert(0, memory_id)
        if len(self._working_memory) > self._working_memory_size:
            self._working_memory = self._working_memory[:self._working_memory_size]

    # ------------------------------------------------------------------
    # Consolidation
    # ------------------------------------------------------------------

    def consolidate(self, threshold: float = 0.7) -> int:
        """Consolidate short-term memories to long-term."""
        count = self._layer.consolidate(threshold)
        self._consolidation_count += 1
        return count

    def get_consolidation_count(self) -> int:
        """Number of consolidation cycles run."""
        return self._consolidation_count

    # ------------------------------------------------------------------
    # Compression
    # ------------------------------------------------------------------

    def compress_conversation(
        self,
        memory_ids: list[str],
        summary: str = "",
    ) -> str:
        """Compress a conversation into a compressed memory."""
        contents = []
        for mid in memory_ids:
            mem = self._layer._memories.get(mid)
            if mem is not None:
                contents.append(str(mem.content))

        combined = "\n".join(contents)
        effective_summary = summary or self._auto_summarize(combined)

        compressed = CompressedMemory(
            compression_type=CompressedMemoryType.CONVERSATION,
            source_ids=list(memory_ids),
            content=combined,
            summary=effective_summary,
            importance=max(
                (self._layer._memories.get(mid, MemoryItem()).importance for mid in memory_ids),
                default=0.5,
            ),
        )
        self._compressed[compressed.id] = compressed
        self._enforce_compressed_limits()
        return compressed.id

    def compress_project(
        self,
        memory_ids: list[str],
        project_name: str = "",
    ) -> str:
        """Compress project memories into a single compressed memory."""
        compressed = CompressedMemory(
            compression_type=CompressedMemoryType.PROJECT,
            source_ids=list(memory_ids),
            content="",
            summary=f"Project: {project_name or 'unnamed'}",
        )
        self._compressed[compressed.id] = compressed
        self._enforce_compressed_limits()
        return compressed.id

    def get_compressed(self, compressed_id: str) -> Optional[CompressedMemory]:
        """Retrieve a compressed memory."""
        return self._compressed.get(compressed_id)

    def expand_compressed(self, compressed_id: str) -> list[MemoryItem]:
        """Expand a compressed memory back into original memories."""
        compressed = self._compressed.get(compressed_id)
        if compressed is None:
            return []
        return [
            self._layer._memories[mid]
            for mid in compressed.source_ids
            if mid in self._layer._memories
        ]

    def list_compressed(
        self,
        compression_type: Optional[CompressedMemoryType] = None,
    ) -> list[CompressedMemory]:
        """List compressed memories, optionally filtered by type."""
        if compression_type is None:
            return list(self._compressed.values())
        return [
            c for c in self._compressed.values()
            if c.compression_type == compression_type
        ]

    def _enforce_compressed_limits(self) -> None:
        """Remove oldest compressed memories when over limit."""
        if len(self._compressed) <= self._max_compressed:
            return
        sorted_compressed = sorted(
            self._compressed.values(),
            key=lambda c: c.created_at,
        )
        excess = len(self._compressed) - self._max_compressed
        for c in sorted_compressed[:excess]:
            del self._compressed[c.id]

    # ------------------------------------------------------------------
    # Snapshots & Versioning
    # ------------------------------------------------------------------

    def create_snapshot(
        self,
        label: str = "",
        memory_ids: Optional[list[str]] = None,
    ) -> str:
        """Create a point-in-time snapshot of memories."""
        if memory_ids is None:
            memory_ids = [
                mid for mid, m in self._layer._memories.items()
                if m.memory_type != MemoryType.ARCHIVED
            ]

        version = self._snapshot_versions.get(label, 0) + 1
        self._snapshot_versions[label] = version

        snapshot = MemorySnapshot(
            version=version,
            label=label or f"snapshot_{version}",
            memory_ids=list(memory_ids),
            summary=f"Snapshot v{version}: {len(memory_ids)} memories",
        )
        self._snapshots[snapshot.id] = snapshot
        return snapshot.id

    def get_snapshot(self, snapshot_id: str) -> Optional[MemorySnapshot]:
        """Retrieve a snapshot by ID."""
        return self._snapshots.get(snapshot_id)

    def list_snapshots(self, label: str = "") -> list[MemorySnapshot]:
        """List snapshots, optionally filtered by label."""
        if label:
            return [s for s in self._snapshots.values() if s.label == label]
        return sorted(
            self._snapshots.values(),
            key=lambda s: s.version,
        )

    def restore_snapshot(self, snapshot_id: str) -> list[MemoryItem]:
        """Restore working memory to a snapshot state."""
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot is None:
            return []
        self._working_memory = list(snapshot.memory_ids)
        return [
            self._layer._memories[mid]
            for mid in snapshot.memory_ids
            if mid in self._layer._memories
        ]

    # ------------------------------------------------------------------
    # Memory Replay
    # ------------------------------------------------------------------

    def replay(
        self,
        memory_ids: list[str],
        chronological: bool = True,
    ) -> list[MemoryItem]:
        """Replay a sequence of memories in order."""
        items = [
            self._layer._memories[mid]
            for mid in memory_ids
            if mid in self._layer._memories
        ]
        if chronological:
            items.sort(key=lambda m: m.created_at)
        return items

    def replay_session(self, session_id: str) -> list[MemoryItem]:
        """Replay all memories associated with a session."""
        items = [
            m for m in self._layer._memories.values()
            if m.metadata.get("session_id") == session_id
        ]
        items.sort(key=lambda m: m.created_at)
        return items

    # ------------------------------------------------------------------
    # Memory Graph
    # ------------------------------------------------------------------

    def link_memories(
        self,
        source_id: str,
        target_id: str,
        relationship: str = "related_to",
    ) -> None:
        """Create a graph edge between two memories."""
        if source_id not in self._layer._memories:
            return
        if target_id not in self._layer._memories:
            return

        node = self._graph.setdefault(source_id, MemoryGraphNode(memory_id=source_id))
        node.edges[target_id] = relationship

    def get_related(
        self,
        memory_id: str,
        relationship: str = "",
        depth: int = 1,
    ) -> list[tuple[MemoryItem, str]]:
        """Get memories related to the given memory."""
        if memory_id not in self._graph:
            return []

        visited: set[str] = {memory_id}
        frontier = [memory_id]
        results: list[tuple[MemoryItem, str]] = []

        for _ in range(depth):
            next_frontier: list[str] = []
            for current in frontier:
                node = self._graph.get(current)
                if node is None:
                    continue
                for target, rel in node.edges.items():
                    if target in visited:
                        continue
                    visited.add(target)
                    if not relationship or rel == relationship:
                        mem = self._layer._memories.get(target)
                        if mem is not None:
                            results.append((mem, rel))
                    next_frontier.append(target)
            frontier = next_frontier
            if not frontier:
                break

        return results

    def get_graph_stats(self) -> dict[str, Any]:
        """Get statistics about the memory graph."""
        nodes = len(self._graph)
        edges = sum(len(n.edges) for n in self._graph.values())
        return {
            "nodes": nodes,
            "edges": edges,
            "density": edges / max(1, nodes * (nodes - 1)),
        }

    # ------------------------------------------------------------------
    # Memory Expiration
    # ------------------------------------------------------------------

    def prune(
        self,
        max_age_seconds: float = 3600.0,
        min_importance: float = 0.0,
    ) -> int:
        """Prune old or unimportant memories."""
        count = self._layer.prune(max_age_seconds)

        if min_importance > 0:
            to_remove = [
                mid for mid, m in self._layer._memories.items()
                if m.memory_type == MemoryType.SHORT_TERM
                and m.importance < min_importance
                and time.time() - m.last_accessed > max_age_seconds
            ]
            for mid in to_remove:
                if mid in self._layer._memories:
                    del self._layer._memories[mid]
                    count += 1

        for mid in list(self._working_memory):
            if mid not in self._layer._memories:
                self._working_memory.remove(mid)

        for mid in list(self._graph.keys()):
            if mid not in self._layer._memories:
                del self._graph[mid]

        return count

    # ------------------------------------------------------------------
    # Summarization
    # ------------------------------------------------------------------

    @staticmethod
    def _auto_summarize(content: str, max_length: int = 200) -> str:
        """Create a simple summary by truncation and key-line extraction."""
        lines = content.strip().split("\n")
        if len(lines) <= 3:
            return content[:max_length]
        first = lines[0][:max_length // 2]
        last = lines[-1][:max_length // 2] if lines[-1].strip() else ""
        if last:
            return f"{first} ... {last}"
        return first[:max_length]

    def summarize_memories(
        self,
        memory_ids: list[str],
        max_length: int = 500,
    ) -> str:
        """Summarize a collection of memory contents."""
        contents = []
        for mid in memory_ids:
            mem = self._layer._memories.get(mid)
            if mem is not None:
                contents.append(str(mem.content))
        combined = " | ".join(contents)
        return self._auto_summarize(combined, max_length)

    # ------------------------------------------------------------------
    # Context Window Management
    # ------------------------------------------------------------------

    def get_context_window(
        self,
        max_tokens: int = 4000,
        chars_per_token: float = 4.0,
        query: str = "",
    ) -> list[Any]:
        """Build a context window fitting within a token budget."""
        budget_chars = int(max_tokens * chars_per_token)
        relevant = self.retrieve_relevant(count=50, query=query)

        window: list[Any] = []
        used = 0
        for mem in relevant:
            content_str = str(mem.content or "")
            if used + len(content_str) > budget_chars:
                continue
            window.append(mem.content)
            used += len(content_str)

        return window

    def compress_context(
        self,
        context: list[Any],
        target_tokens: int = 2000,
        chars_per_token: float = 4.0,
    ) -> str:
        """Compress a context list to fit within a target token budget."""
        target_chars = int(target_tokens * chars_per_token)
        combined = " | ".join(str(c) for c in context)
        if len(combined) <= target_chars:
            return combined
        return self._auto_summarize(combined, target_chars)

    def expand_context(self, compressed: str, detail_level: int = 2) -> str:
        """Expand a compressed context back to more detail."""
        parts = compressed.split(" | ")
        if detail_level >= 3:
            return "\n".join(f"- {p}" for p in parts)
        if detail_level >= 2:
            return " | ".join(parts)
        return compressed[:500]

    # ------------------------------------------------------------------
    # Stats & Cleanup
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive memory system statistics."""
        memories = self._layer._memories
        counts = {
            "short_term": sum(1 for m in memories.values() if m.memory_type == MemoryType.SHORT_TERM),
            "long_term": sum(1 for m in memories.values() if m.memory_type == MemoryType.LONG_TERM),
            "archived": sum(1 for m in memories.values() if m.memory_type == MemoryType.ARCHIVED),
            "working": len(self._working_memory),
            "compressed": len(self._compressed),
            "snapshots": len(self._snapshots),
            "total": len(memories),
        }
        graph = self.get_graph_stats()
        return {
            "memory_counts": counts,
            "memory_graph": graph,
            "consolidation_count": self._consolidation_count,
            "pinned": len(self._pinned),
            "avg_importance": (
                sum(m.importance for m in memories.values()) / max(1, len(memories))
            ),
        }

    def clear(self) -> None:
        """Remove all memories, compressed, snapshots, and graph data."""
        self._layer.clear()
        self._working_memory.clear()
        self._compressed.clear()
        self._snapshots.clear()
        self._snapshot_versions.clear()
        self._graph.clear()
        self._search.clear()
        self._consolidation_count = 0
        self._pinned.clear()
        self._layer.protected_ids.clear()
