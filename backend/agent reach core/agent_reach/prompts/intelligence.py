"""
Prompt Intelligence (M7.7).

Enhanced prompt management with dynamic building, ranking,
optimization, learning, and automatic selection.

Extends the existing PromptLibrary from Milestone 6.6.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from prompts.library import PromptLibrary, PromptTemplate


class PromptRankingMethod(str, Enum):
    """How prompts are ranked."""
    SCORE = "score"          # By evaluation score
    USAGE = "usage"          # By usage frequency
    RECENCY = "recency"      # Most recently used
    EFFECTIVENESS = "effectiveness"  # Composite effectiveness


@dataclass
class PromptRanking:
    """Ranked prompt with metadata."""
    prompt: PromptTemplate
    score: float = 0.0
    usage_count: int = 0
    avg_rating: float = 0.0
    last_used: float = 0.0


@dataclass
class PromptLearningEntry:
    """Learning data for a prompt."""
    prompt_name: str
    variables_used: dict[str, Any] = field(default_factory=dict)
    output_quality: float = 0.0
    latency_ms: float = 0.0
    provider: str = ""
    timestamp: float = field(default_factory=time.time)
    notes: str = ""


class PromptIntelligence:
    """Intelligent prompt management and optimization.

    Extends PromptLibrary with:
    - Dynamic prompt building
    - Prompt ranking by multiple methods
    - Prompt optimization suggestions
    - Prompt learning from usage data
    - Automatic prompt selection
    """

    def __init__(self) -> None:
        self._library = PromptLibrary()
        self._usage: dict[str, int] = defaultdict(int)
        self._ratings: dict[str, list[float]] = defaultdict(list)
        self._last_used: dict[str, float] = {}
        self._learning: list[PromptLearningEntry] = []

    @property
    def library(self) -> PromptLibrary:
        return self._library

    # ------------------------------------------------------------------
    # Dynamic building
    # ------------------------------------------------------------------

    def build_prompt(
        self,
        task: str,
        context: Optional[dict[str, Any]] = None,
        style: str = "default",
    ) -> str:
        """Dynamically build a prompt based on task and context.

        Args:
            task: The task description.
            context: Optional variables to inject.
            style: Prompt style (default, concise, detailed, creative).

        Returns:
            Constructed prompt string.
        """
        ctx = context or {}
        style_prefixes = {
            "default": "",
            "concise": "Be concise and direct. ",
            "detailed": "Provide a comprehensive and detailed response. ",
            "creative": "Be creative and think outside the box. ",
        }

        prefix = style_prefixes.get(style, "")
        parts = [f"{prefix}{task}"]

        if ctx:
            parts.append("\nContext:")
            for key, value in ctx.items():
                parts.append(f"  {key}: {value}")

        return "\n".join(parts)

    def select_best_prompt(
        self,
        task_type: str = "",
        method: PromptRankingMethod = PromptRankingMethod.EFFECTIVENESS,
    ) -> Optional[PromptTemplate]:
        """Automatically select the best prompt for a task type.

        Args:
            task_type: The type of task (e.g., "summarization", "coding").
            method: Ranking method to use.

        Returns:
            Best matching PromptTemplate or None.
        """
        candidates = self._library.search(task_type)
        if not candidates:
            candidates = self._library.list_prompts()
        if not candidates:
            return None

        ranked = self.rank_prompts(candidates, method=method)
        return ranked[0].prompt if ranked else None

    # ------------------------------------------------------------------
    # Ranking
    # ------------------------------------------------------------------

    def rank_prompts(
        self,
        prompts: list[PromptTemplate],
        method: PromptRankingMethod = PromptRankingMethod.EFFECTIVENESS,
    ) -> list[PromptRanking]:
        """Rank prompts by the specified method."""
        rankings: list[PromptRanking] = []

        for prompt in prompts:
            usage_count = self._usage.get(prompt.name, 0)
            ratings = self._ratings.get(prompt.name, [])
            avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
            last_used = self._last_used.get(prompt.name, 0.0)

            if method == PromptRankingMethod.SCORE:
                score = self._compute_score(prompt, avg_rating)
            elif method == PromptRankingMethod.USAGE:
                score = float(usage_count)
            elif method == PromptRankingMethod.RECENCY:
                score = last_used
            else:  # effectiveness
                score = (
                    avg_rating * 0.5
                    + min(1.0, usage_count / 100.0) * 0.3
                    + min(1.0, last_used / (time.time() + 1)) * 0.2
                )

            rankings.append(
                PromptRanking(
                    prompt=prompt,
                    score=score,
                    usage_count=usage_count,
                    avg_rating=avg_rating,
                    last_used=last_used,
                )
            )

        rankings.sort(key=lambda r: r.score, reverse=True)
        return rankings

    # ------------------------------------------------------------------
    # Optimization
    # ------------------------------------------------------------------

    def suggest_optimizations(self, prompt_name: str) -> list[str]:
        """Suggest optimizations for a prompt template."""
        prompt = self._library.get(prompt_name)
        if prompt is None:
            return []

        suggestions: list[str] = []

        # Check template length
        if len(prompt.template) > 2000:
            suggestions.append(
                "Prompt is very long (>2000 chars). Consider shortening for better latency."
            )
        if len(prompt.template) < 50:
            suggestions.append(
                "Prompt is very short (<50 chars). Consider adding more detail for clarity."
            )

        # Check variable usage
        if not prompt.variables:
            suggestions.append(
                "No variables defined. Consider using variables for reusability."
            )

        # Check description
        if not prompt.description:
            suggestions.append("Add a description to improve discoverability.")

        # Check tags
        if not prompt.tags:
            suggestions.append("Add tags to improve categorization and search.")

        # Check ratings
        ratings = self._ratings.get(prompt_name, [])
        if ratings and sum(ratings) / len(ratings) < 0.5:
            suggestions.append(
                "Average rating is low. Consider revising the template content."
            )

        return suggestions

    # ------------------------------------------------------------------
    # Learning
    # ------------------------------------------------------------------

    def record_usage(
        self,
        prompt_name: str,
        variables: dict[str, Any] | None = None,
        output_quality: float = 0.5,
        latency_ms: float = 0.0,
        provider: str = "",
    ) -> None:
        """Record usage data for a prompt to enable learning."""
        self._usage[prompt_name] += 1
        self._last_used[prompt_name] = time.time()

        if output_quality:
            self._ratings[prompt_name].append(output_quality)

        entry = PromptLearningEntry(
            prompt_name=prompt_name,
            variables_used=dict(variables or {}),
            output_quality=output_quality,
            latency_ms=latency_ms,
            provider=provider,
        )
        self._learning.append(entry)

    def get_learning_stats(self, prompt_name: str = "") -> dict[str, Any]:
        """Get learning statistics for prompts."""
        entries = self._learning
        if prompt_name:
            entries = [e for e in entries if e.prompt_name == prompt_name]

        if not entries:
            return {"total_uses": 0}

        return {
            "total_uses": len(entries),
            "avg_quality": sum(e.output_quality for e in entries) / len(entries)
            if entries
            else 0.0,
            "avg_latency_ms": sum(e.latency_ms for e in entries) / len(entries)
            if entries
            else 0.0,
            "providers_used": list(set(e.provider for e in entries if e.provider)),
            "most_used_variables": self._most_used_variables(entries),
        }

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get prompt intelligence statistics."""
        lib_stats = self._library.get_stats()
        return {
            **lib_stats,
            "total_usage": sum(self._usage.values()),
            "learning_entries": len(self._learning),
            "rated_prompts": len(self._ratings),
        }

    def clear(self) -> None:
        """Clear all data."""
        self._library.clear()
        self._usage.clear()
        self._ratings.clear()
        self._last_used.clear()
        self._learning.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_score(prompt: PromptTemplate, avg_rating: float) -> float:
        """Compute a quality score for a prompt."""
        score = avg_rating * 0.6
        # Bonus for having description and tags
        if prompt.description:
            score += 0.1
        if prompt.tags:
            score += 0.1
        if prompt.variables:
            score += 0.1
        # Bonus for reasonable length
        if 100 <= len(prompt.template) <= 1500:
            score += 0.1
        return min(1.0, score)

    @staticmethod
    def _most_used_variables(entries: list[PromptLearningEntry]) -> dict[str, int]:
        """Get the most commonly used variables."""
        counts: dict[str, int] = defaultdict(int)
        for entry in entries:
            for var in entry.variables_used:
                counts[var] += 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10])
