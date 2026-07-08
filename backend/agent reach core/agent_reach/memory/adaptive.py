"""
Adaptive Memory Evolution (M9.21).

Layer: Application — composes the EXISTING LongCatMemoryEngine. Every
primitive it invokes already exists on the engine:

    compression      → compress_conversation / list_compressed (M7)
    consolidation    → consolidate (M7)
    summarization    → summarize_memories (M7)
    relevance        → MemoryRanker scores (M7)
    pinning          → pin/unpin protection (M9.7)

M9.21 adds the two missing behaviors as a policy layer:

- Intelligent forgetting: archive-then-delete lifecycle driven by a
  documented MemoryPolicy (age, importance, access count). Pinned
  memories are never touched (the M9.7 guarantee). Forgetting is
  two-phase: low-value SHORT_TERM memories are archived first;
  archived memories that stay unused past a retention window are
  deleted. Every phase reports exactly what it did.
- optimize(): one entry point that runs the full evolution pass
  (consolidate → forget → compress crowded sessions) and returns the
  real before/after stats. This is what the M9.14 optimization
  engine and the M9.27 loop can call.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from memory.layer import MemoryType
from memory.longcat import LongCatMemoryEngine


@dataclass
class MemoryPolicy:
    """Documented thresholds driving adaptive evolution.

    Attributes:
        archive_age_seconds: SHORT_TERM memories older than this
            (since last access) become forgetting candidates.
        archive_max_importance: only memories at or below this
            importance can be archived by the policy.
        archive_max_access_count: only memories accessed at most this
            many times can be archived (frequently used memories are
            evidently valuable regardless of importance score).
        delete_after_archived_seconds: ARCHIVED memories unused for
            this long are permanently deleted.
        consolidate_threshold: score threshold forwarded to the
            engine's consolidate().
        compress_session_min_items: sessions with at least this many
            items get compressed during optimize().
    """

    archive_age_seconds: float = 3600.0
    archive_max_importance: float = 0.4
    archive_max_access_count: int = 2
    delete_after_archived_seconds: float = 24 * 3600.0
    consolidate_threshold: float = 0.7
    compress_session_min_items: int = 10

    def validate(self) -> None:
        if self.archive_age_seconds < 0 or self.delete_after_archived_seconds < 0:
            raise ValueError("age thresholds must be >= 0")
        if not 0.0 <= self.archive_max_importance <= 1.0:
            raise ValueError("archive_max_importance must be within [0, 1]")
        if self.archive_max_access_count < 0:
            raise ValueError("archive_max_access_count must be >= 0")


@dataclass
class EvolutionReport:
    """What one adaptive pass actually did — real counts only."""

    started_at: float = field(default_factory=time.time)
    consolidated: int = 0
    archived: int = 0
    deleted: int = 0
    compressed_sessions: list[str] = field(default_factory=list)
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "consolidated": self.consolidated,
            "archived": self.archived,
            "deleted": self.deleted,
            "compressed_sessions": list(self.compressed_sessions),
            "before": dict(self.before),
            "after": dict(self.after),
        }


class AdaptiveMemoryManager:
    """Policy-driven evolution over the shared LongCat engine."""

    def __init__(
        self,
        engine: LongCatMemoryEngine,
        policy: Optional[MemoryPolicy] = None,
    ) -> None:
        self._engine = engine
        self._policy = policy or MemoryPolicy()
        self._policy.validate()
        self._archived_at: dict[str, float] = {}
        self._reports: list[EvolutionReport] = []

    @property
    def engine(self) -> LongCatMemoryEngine:
        return self._engine

    @property
    def policy(self) -> MemoryPolicy:
        return self._policy

    # ── Intelligent forgetting ──────────────────────────────────

    def forget(self) -> tuple[int, int]:
        """Two-phase forgetting per policy. Returns (archived, deleted).

        Phase 1 — archive: old, unimportant, rarely-accessed
        SHORT_TERM memories are archived (recoverable).
        Phase 2 — delete: memories archived by THIS manager that
        stayed unused past the retention window are deleted through
        the engine's real delete() (index/graph/working cleanup).
        Pinned memories are exempt from both phases.
        """
        now = time.perf_counter()
        wall_now = time.time()
        policy = self._policy
        archived = 0
        deleted = 0

        # Phase 1: archive candidates.
        for memory_id, item in list(self._engine._layer._memories.items()):
            if item.memory_type != MemoryType.SHORT_TERM:
                continue
            if self._engine.is_pinned(memory_id):
                continue
            age = now - item.last_accessed
            if (
                age > policy.archive_age_seconds
                and item.importance <= policy.archive_max_importance
                and item.access_count <= policy.archive_max_access_count
            ):
                if self._engine._layer.archive(memory_id):
                    self._archived_at[memory_id] = wall_now
                    archived += 1

        # Phase 2: delete expired archived memories.
        for memory_id, archived_time in list(self._archived_at.items()):
            item = self._engine._layer._memories.get(memory_id)
            if item is None:
                del self._archived_at[memory_id]
                continue
            if item.memory_type != MemoryType.ARCHIVED:
                # was revived (promoted/re-typed) — stop tracking
                del self._archived_at[memory_id]
                continue
            if self._engine.is_pinned(memory_id):
                continue
            if wall_now - archived_time > policy.delete_after_archived_seconds:
                if self._engine.delete(memory_id):
                    deleted += 1
                del self._archived_at[memory_id]

        return archived, deleted

    # ── Full evolution pass ─────────────────────────────────────

    def optimize(self) -> EvolutionReport:
        """Consolidate → forget → compress crowded sessions.

        Every number in the report is a real engine measurement.
        """
        report = EvolutionReport()
        report.before = dict(self._engine.get_stats()["memory_counts"])

        report.consolidated = self._engine.consolidate(
            threshold=self._policy.consolidate_threshold
        )
        report.archived, report.deleted = self.forget()

        # Compress sessions that grew past the policy threshold.
        session_items: dict[str, list[str]] = {}
        for memory_id, item in self._engine._layer._memories.items():
            session_id = str(item.metadata.get("session_id", ""))
            if session_id:
                session_items.setdefault(session_id, []).append(memory_id)
        for session_id, ids in session_items.items():
            if len(ids) >= self._policy.compress_session_min_items:
                self._engine.compress_conversation(ids)
                report.compressed_sessions.append(session_id)

        report.after = dict(self._engine.get_stats()["memory_counts"])
        self._reports.append(report)
        if len(self._reports) > 100:
            self._reports = self._reports[-100:]
        return report

    # ── Introspection ───────────────────────────────────────────

    def get_reports(self, limit: int = 20) -> list[EvolutionReport]:
        """Past evolution reports, newest first."""
        return list(reversed(self._reports))[: max(0, limit)]

    def get_status(self) -> dict[str, Any]:
        return {
            "policy": {
                "archive_age_seconds": self._policy.archive_age_seconds,
                "archive_max_importance": self._policy.archive_max_importance,
                "archive_max_access_count": self._policy.archive_max_access_count,
                "delete_after_archived_seconds": self._policy.delete_after_archived_seconds,
                "consolidate_threshold": self._policy.consolidate_threshold,
                "compress_session_min_items": self._policy.compress_session_min_items,
            },
            "tracked_archived": len(self._archived_at),
            "total_passes": len(self._reports),
            "memory_counts": dict(self._engine.get_stats()["memory_counts"]),
        }

    def clear(self) -> None:
        self._archived_at.clear()
        self._reports.clear()
