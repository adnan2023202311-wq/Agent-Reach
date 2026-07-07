"""
Context Engine (M7.2).

An intelligent context manager that builds, ranks, and optimizes
context for LLM interactions. Features:

- Dynamic Context Builder
- Context Ranking & Priority Scoring
- Duplicate Removal
- Automatic Token Budget Management
- Adaptive Context Selection
- Prompt Context Builder
- Context Compression Pipeline
- Long Conversation Support
- Context Metadata

Layer: Application/Core — depends inward on domain/ and infrastructure/ only.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ContextPriority(str, Enum):
    """Priority level for context items."""
    CRITICAL = "critical"    # Must always be included
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    OPTIONAL = "optional"    # Only included if budget allows


@dataclass
class ContextItem:
    """A single item in the context window.

    Attributes:
        id: Unique identifier.
        content: The content string.
        priority: Priority level.
        source: Where this context came from (e.g., "memory", "conversation", "system").
        created_at: When the item was created.
        tokens_estimate: Estimated token count.
        metadata: Arbitrary additional metadata.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    priority: ContextPriority = ContextPriority.MEDIUM
    source: str = ""
    created_at: float = field(default_factory=time.time)
    tokens_estimate: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """Content-based hash for deduplication."""
        return hashlib.md5(self.content.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content[:200] + "..." if len(self.content) > 200 else self.content,
            "priority": self.priority.value,
            "source": self.source,
            "tokens_estimate": self.tokens_estimate,
            "metadata": dict(self.metadata),
        }


@dataclass
class ContextWindow:
    """A built context window ready for LLM consumption.

    Attributes:
        items: Ordered list of context items.
        total_tokens: Estimated total token count.
        budget: Token budget for this window.
        usage_pct: Percentage of budget used.
        metadata: Build metadata.
    """

    items: list[ContextItem] = field(default_factory=list)
    total_tokens: int = 0
    budget: int = 4096
    usage_pct: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_text(self, separator: str = "\n---\n") -> str:
        """Render the context window as a single text string."""
        return separator.join(item.content for item in self.items)

    def to_messages(
        self, system_role: str = "system"
    ) -> list[dict[str, str]]:
        """Render as a list of role/content message dicts."""
        messages: list[dict[str, str]] = []
        for item in self.items:
            messages.append({"role": system_role, "content": item.content})
        return messages


# ---------------------------------------------------------------------------
# Context Ranker
# ---------------------------------------------------------------------------


class ContextRanker:
    """Scores and ranks context items by priority, freshness, and relevance."""

    _PRIORITY_SCORES: dict[ContextPriority, float] = {
        ContextPriority.CRITICAL: 100.0,
        ContextPriority.HIGH: 75.0,
        ContextPriority.MEDIUM: 50.0,
        ContextPriority.LOW: 25.0,
        ContextPriority.OPTIONAL: 10.0,
    }

    def __init__(
        self,
        priority_weight: float = 0.5,
        recency_weight: float = 0.3,
        relevance_weight: float = 0.2,
    ) -> None:
        self._priority_weight = priority_weight
        self._recency_weight = recency_weight
        self._relevance_weight = relevance_weight

    def score(
        self,
        item: ContextItem,
        *,
        query: str = "",
        now: Optional[float] = None,
    ) -> float:
        """Compute a composite relevance score for a context item."""
        now = now or time.time()

        # Priority score (normalized to 0-1)
        priority_score = self._PRIORITY_SCORES.get(item.priority, 50.0) / 100.0

        # Recency score
        age = now - item.created_at
        recency_score = 1.0 / (1.0 + age / 3600.0)

        # Relevance score (substring match)
        relevance_score = 0.0
        if query:
            content_lower = item.content.lower()
            query_lower = query.lower()
            if query_lower in content_lower:
                relevance_score = 0.5 + 0.5 * (
                    len(query_lower) / max(1, len(content_lower))
                )

        return (
            self._priority_weight * priority_score
            + self._recency_weight * recency_score
            + self._relevance_weight * relevance_score
        )

    def rank(
        self,
        items: list[ContextItem],
        *,
        query: str = "",
        limit: Optional[int] = None,
    ) -> list[ContextItem]:
        """Rank context items by score, returning top items."""
        now = time.time()
        scored = [(item, self.score(item, query=query, now=now)) for item in items]
        scored.sort(key=lambda x: x[1], reverse=True)
        result = [item for item, _ in scored]
        if limit is not None:
            return result[:limit]
        return result


# ---------------------------------------------------------------------------
# Context Builder
# ---------------------------------------------------------------------------


class ContextBuilder:
    """Builds optimized context windows for LLM consumption."""

    def __init__(
        self,
        chars_per_token: float = 4.0,
        max_context_items: int = 100,
    ) -> None:
        self._chars_per_token = chars_per_token
        self._max_context_items = max_context_items
        self._ranker = ContextRanker()
        self._seen_hashes: set[str] = set()

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count from character count."""
        return max(1, int(len(text) / self._chars_per_token))

    def add_item(
        self,
        content: str,
        priority: ContextPriority = ContextPriority.MEDIUM,
        source: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ContextItem:
        """Create a context item with token estimation."""
        item = ContextItem(
            content=content,
            priority=priority,
            source=source,
            tokens_estimate=self.estimate_tokens(content),
            metadata=metadata or {},
        )
        return item

    def build_window(
        self,
        items: list[ContextItem],
        *,
        budget: int = 4096,
        query: str = "",
        deduplicate: bool = True,
        prioritize: bool = True,
    ) -> ContextWindow:
        """Build an optimized context window within a token budget.

        Args:
            items: All available context items.
            budget: Maximum token budget.
            query: Optional query for relevance ranking.
            deduplicate: Remove duplicate items by content hash.
            prioritize: Sort by rank before filling budget.

        Returns:
            ContextWindow with optimized context items.
        """
        # Deduplicate
        working = items
        if deduplicate:
            working = self._deduplicate(items)

        # Rank by priority/recency/relevance
        if prioritize:
            working = self._ranker.rank(working, query=query)

        # Fill budget (always include CRITICAL items first)
        critical = [i for i in working if i.priority == ContextPriority.CRITICAL]
        non_critical = [i for i in working if i.priority != ContextPriority.CRITICAL]

        window_items: list[ContextItem] = []
        tokens_used = 0

        # Include all critical items
        for item in critical:
            if len(window_items) >= self._max_context_items:
                break
            window_items.append(item)
            tokens_used += item.tokens_estimate

        # Fill remaining budget with ranked items
        for item in non_critical:
            if len(window_items) >= self._max_context_items:
                break
            if tokens_used + item.tokens_estimate > budget:
                continue
            window_items.append(item)
            tokens_used += item.tokens_estimate

        usage_pct = (tokens_used / budget * 100) if budget > 0 else 0.0

        return ContextWindow(
            items=window_items,
            total_tokens=tokens_used,
            budget=budget,
            usage_pct=usage_pct,
            metadata={
                "critical_count": len(critical),
                "total_available": len(items),
                "deduplicated": deduplicate,
                "query": query,
            },
        )

    def _deduplicate(self, items: list[ContextItem]) -> list[ContextItem]:
        """Remove duplicate context items by content hash."""
        seen: set[str] = set()
        unique: list[ContextItem] = []
        for item in items:
            h = item.content_hash
            if h not in seen:
                seen.add(h)
                unique.append(item)
        return unique

    def reset_dedup(self) -> None:
        """Reset the deduplication cache."""
        self._seen_hashes.clear()


# ---------------------------------------------------------------------------
# Context Compression Pipeline
# ---------------------------------------------------------------------------


class ContextCompressor:
    """Compresses context to fit within token budgets."""

    def __init__(self, chars_per_token: float = 4.0) -> None:
        self._chars_per_token = chars_per_token

    def compress(
        self,
        text: str,
        target_tokens: int,
        *,
        strategy: str = "truncate",
    ) -> str:
        """Compress text to fit within target token budget.

        Strategies:
        - truncate: simple truncation
        - summarize: extract key sentences (first + last)
        - hybrid: try summarize, fall back to truncate
        """
        target_chars = int(target_tokens * self._chars_per_token)
        if len(text) <= target_chars:
            return text

        if strategy == "truncate":
            return self._truncate(text, target_chars)

        if strategy == "summarize":
            return self._summarize(text, target_chars)

        # hybrid
        result = self._summarize(text, target_chars)
        if len(result) > target_chars:
            result = self._truncate(result, target_chars)
        return result

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        """Truncate text to max_chars, preserving word boundaries."""
        if len(text) <= max_chars:
            return text
        truncated = text[:max_chars]
        # Try to break at last space
        last_space = truncated.rfind(" ")
        if last_space > max_chars // 2:
            return truncated[:last_space] + "..."
        return truncated + "..."

    @staticmethod
    def _summarize(text: str, max_chars: int) -> str:
        """Extract key sentences: first + last meaningful lines."""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if not lines:
            return text[:max_chars]

        if len(lines) <= 3:
            return " | ".join(lines)[:max_chars]

        half = max_chars // 2
        first = lines[0][:half]
        last = lines[-1][:half]
        return f"{first} ... {last}"

    def compress_items(
        self,
        items: list[ContextItem],
        budget: int,
    ) -> list[ContextItem]:
        """Compress a list of context items to fit within budget."""
        total_tokens = sum(i.tokens_estimate for i in items)
        if total_tokens <= budget:
            return items

        # First, drop OPTIONAL items
        working = [i for i in items if i.priority != ContextPriority.OPTIONAL]
        total_tokens = sum(i.tokens_estimate for i in working)
        if total_tokens <= budget:
            return working

        # Then, drop LOW priority items
        working_low = [i for i in working if i.priority == ContextPriority.LOW]
        keep = [i for i in working if i.priority != ContextPriority.LOW]
        total_keep = sum(i.tokens_estimate for i in keep)
        if total_keep <= budget:
            return keep
        # Add low items back only if budget permits
        working = keep

        # Separate by priority
        critical_high = [
            i for i in working
            if i.priority in (ContextPriority.CRITICAL, ContextPriority.HIGH)
        ]
        medium = [i for i in working if i.priority == ContextPriority.MEDIUM]

        critical_high_tokens = sum(i.tokens_estimate for i in critical_high)
        remaining_budget = budget - critical_high_tokens

        if remaining_budget <= 0:
            # Even critical/high items exceed budget; compress them proportionally
            budget_per_item = max(10, budget // max(1, len(working)))
            for item in working:
                item.content = self.compress(item.content, budget_per_item)
                item.tokens_estimate = budget_per_item
            return working

        # Compress medium items to fit remaining budget
        if medium:
            budget_per_medium = max(10, remaining_budget // len(medium))
            for item in medium:
                item.content = self.compress(item.content, budget_per_medium)
                item.tokens_estimate = budget_per_medium

        return working


# ---------------------------------------------------------------------------
# Context Engine
# ---------------------------------------------------------------------------


class ContextEngine:
    """Intelligent context manager for LLM interactions.

    Combines context building, ranking, deduplication, compression,
    and token budget management into a single interface.
    """

    def __init__(
        self,
        default_budget: int = 4096,
        chars_per_token: float = 4.0,
        max_context_items: int = 100,
    ) -> None:
        self._default_budget = default_budget
        self._builder = ContextBuilder(
            chars_per_token=chars_per_token,
            max_context_items=max_context_items,
        )
        self._compressor = ContextCompressor(chars_per_token=chars_per_token)
        self._items: list[ContextItem] = []
        self._build_count: int = 0

    # ------------------------------------------------------------------
    # Context item management
    # ------------------------------------------------------------------

    def add(
        self,
        content: str,
        priority: ContextPriority = ContextPriority.MEDIUM,
        source: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a context item and return its ID."""
        item = self._builder.add_item(
            content=content,
            priority=priority,
            source=source,
            metadata=metadata,
        )
        self._items.append(item)
        return item.id

    def add_items(self, items: list[ContextItem]) -> None:
        """Bulk-add context items."""
        self._items.extend(items)

    def remove(self, item_id: str) -> bool:
        """Remove a context item by ID."""
        for i, item in enumerate(self._items):
            if item.id == item_id:
                self._items.pop(i)
                return True
        return False

    def get_items(
        self,
        source: str = "",
        priority: Optional[ContextPriority] = None,
    ) -> list[ContextItem]:
        """Get context items, optionally filtered."""
        items = self._items
        if source:
            items = [i for i in items if i.source == source]
        if priority is not None:
            items = [i for i in items if i.priority == priority]
        return items

    def clear(self, source: str = "") -> int:
        """Clear context items, optionally by source. Returns count removed."""
        if not source:
            count = len(self._items)
            self._items.clear()
            return count
        before = len(self._items)
        self._items = [i for i in self._items if i.source != source]
        return before - len(self._items)

    # ------------------------------------------------------------------
    # Context building
    # ------------------------------------------------------------------

    def build(
        self,
        *,
        budget: Optional[int] = None,
        query: str = "",
        deduplicate: bool = True,
        include_items: Optional[list[ContextItem]] = None,
    ) -> ContextWindow:
        """Build an optimized context window.

        Args:
            budget: Token budget (defaults to engine's default).
            query: Optional query for relevance ranking.
            deduplicate: Remove duplicates.
            include_items: Additional items to include.

        Returns:
            Optimized ContextWindow.
        """
        effective_budget = budget or self._default_budget

        # Combine engine items with additional items
        all_items = list(self._items)
        if include_items:
            all_items.extend(include_items)

        window = self._builder.build_window(
            all_items,
            budget=effective_budget,
            query=query,
            deduplicate=deduplicate,
        )

        self._build_count += 1
        return window

    def build_for_conversation(
        self,
        messages: list[dict[str, str]],
        system_prompt: str = "",
        *,
        budget: Optional[int] = None,
        query: str = "",
    ) -> ContextWindow:
        """Build context optimized for a conversation.

        System prompt gets CRITICAL priority. Recent messages get
        HIGH priority. Older messages get MEDIUM priority.
        """
        items: list[ContextItem] = []

        if system_prompt:
            items.append(
                self._builder.add_item(
                    content=system_prompt,
                    priority=ContextPriority.CRITICAL,
                    source="system",
                )
            )

        # Messages get higher priority the more recent they are
        total = len(messages)
        for i, msg in enumerate(messages):
            # More recent = higher priority
            if i >= total - 3:
                prio = ContextPriority.HIGH
            elif i >= total - 6:
                prio = ContextPriority.MEDIUM
            else:
                prio = ContextPriority.LOW

            role = msg.get("role", "user")
            content = msg.get("content", "")
            items.append(
                self._builder.add_item(
                    content=f"[{role}]: {content}",
                    priority=prio,
                    source="conversation",
                    metadata={"role": role, "index": i},
                )
            )

        return self.build(
            budget=budget,
            query=query,
            include_items=items,
        )

    def build_with_sources(
        self,
        *,
        system: str = "",
        memories: list[str] = (),
        knowledge: list[str] = (),
        conversation: list[dict[str, str]] = (),
        budget: Optional[int] = None,
        query: str = "",
    ) -> ContextWindow:
        """Build context from multiple named sources.

        Args:
            system: System prompt (CRITICAL).
            memories: Memory items (HIGH).
            knowledge: Knowledge items (MEDIUM).
            conversation: Conversation messages (varies by recency).
            budget: Token budget.
            query: Optional relevance query.
        """
        items: list[ContextItem] = []

        if system:
            items.append(
                self._builder.add_item(system, ContextPriority.CRITICAL, "system")
            )

        for mem in memories:
            items.append(
                self._builder.add_item(mem, ContextPriority.HIGH, "memory")
            )

        for kn in knowledge:
            items.append(
                self._builder.add_item(kn, ContextPriority.MEDIUM, "knowledge")
            )

        total_conv = len(conversation)
        for i, msg in enumerate(conversation):
            if i >= total_conv - 3:
                prio = ContextPriority.HIGH
            elif i >= total_conv - 6:
                prio = ContextPriority.MEDIUM
            else:
                prio = ContextPriority.LOW

            role = msg.get("role", "user")
            content = msg.get("content", "")
            items.append(
                self._builder.add_item(
                    f"[{role}]: {content}",
                    prio,
                    "conversation",
                    {"role": role},
                )
            )

        return self.build(budget=budget, query=query, include_items=items)

    # ------------------------------------------------------------------
    # Compression
    # ------------------------------------------------------------------

    def compress(self, text: str, target_tokens: int, strategy: str = "hybrid") -> str:
        """Compress text to fit within target token budget."""
        return self._compressor.compress(text, target_tokens, strategy=strategy)

    def compress_window(
        self, window: ContextWindow, target_budget: int
    ) -> ContextWindow:
        """Compress an existing context window to a smaller budget."""
        items = self._compressor.compress_items(
            list(window.items), target_budget
        )
        total_tokens = sum(i.tokens_estimate for i in items)
        return ContextWindow(
            items=items,
            total_tokens=total_tokens,
            budget=target_budget,
            usage_pct=(total_tokens / target_budget * 100) if target_budget > 0 else 0,
            metadata={"compressed": True, **window.metadata},
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def item_count(self) -> int:
        """Number of registered context items."""
        return len(self._items)

    def get_stats(self) -> dict[str, Any]:
        """Get context engine statistics."""
        source_counts: dict[str, int] = {}
        priority_counts: dict[str, int] = {}
        total_tokens = 0

        for item in self._items:
            source_counts[item.source] = source_counts.get(item.source, 0) + 1
            priority_counts[item.priority.value] = (
                priority_counts.get(item.priority.value, 0) + 1
            )
            total_tokens += item.tokens_estimate

        return {
            "total_items": len(self._items),
            "total_tokens_estimate": total_tokens,
            "source_distribution": source_counts,
            "priority_distribution": priority_counts,
            "build_count": self._build_count,
            "default_budget": self._default_budget,
        }
