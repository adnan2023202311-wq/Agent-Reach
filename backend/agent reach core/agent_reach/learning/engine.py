"""
Reach Learning Engine (M7.10).

Platform learning from execution history, provider performance,
prompt effectiveness, skill usage, and workflow outcomes.

- Execution Statistics
- Provider Statistics
- Prompt Statistics
- Skill Statistics
- Workflow Statistics
- Learning Cache
- Recommendation Engine
- Automatic Optimization
- Future Decision Improvement

Layer: Application/Core.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ExecutionRecord:
    """A single execution record for learning."""
    id: str = ""
    task: str = ""
    provider: str = ""
    mode: str = ""
    quality: float = 0.0
    latency_ms: float = 0.0
    cost: float = 0.0
    success: bool = True
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderLearning:
    """Aggregated learning about a provider."""
    provider: str = ""
    total_executions: int = 0
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0
    avg_quality: float = 0.0
    avg_cost: float = 0.0
    best_for: list[str] = field(default_factory=list)  # task types


@dataclass
class Recommendation:
    """A learning-based recommendation."""
    category: str = ""
    recommendation: str = ""
    confidence: float = 0.0
    based_on: int = 0  # number of data points
    metadata: dict[str, Any] = field(default_factory=dict)


class ReachLearningEngine:
    """Platform learning engine.

    Learns from all platform activity to improve future decisions.
    """

    def __init__(self, max_history: int = 10000) -> None:
        self._executions: list[ExecutionRecord] = []
        self._max_history = max_history
        self._provider_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"executions": 0, "successes": 0, "total_latency": 0.0, "total_quality": 0.0, "total_cost": 0.0}
        )
        self._task_types: dict[str, list[str]] = defaultdict(list)  # task_type -> [provider]
        self._optimization_suggestions: list[str] = []
        self._generation: int = 0

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        task: str,
        provider: str,
        mode: str = "",
        quality: float = 0.5,
        latency_ms: float = 0.0,
        cost: float = 0.0,
        success: bool = True,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record an execution for learning."""
        record = ExecutionRecord(
            id=str(len(self._executions)),
            task=task,
            provider=provider,
            mode=mode,
            quality=quality,
            latency_ms=latency_ms,
            cost=cost,
            success=success,
            metadata=dict(metadata or {}),
        )
        self._executions.append(record)

        # Update provider stats
        ps = self._provider_stats[provider]
        ps["executions"] += 1
        if success:
            ps["successes"] += 1
        ps["total_latency"] += latency_ms
        ps["total_quality"] += quality
        ps["total_cost"] += cost

        # Track task type associations
        task_type = self._infer_task_type(task)
        self._task_types[task_type].append(provider)

        # Prune if over limit
        if len(self._executions) > self._max_history:
            self._executions = self._executions[-self._max_history:]

    # ------------------------------------------------------------------
    # Provider Learning
    # ------------------------------------------------------------------

    def get_provider_learning(self, provider: str) -> ProviderLearning:
        """Get aggregated learning about a provider."""
        ps = self._provider_stats.get(provider, {})
        n = max(1, ps.get("executions", 0))

        # Best task types
        best_for: list[str] = []
        for task_type, providers in self._task_types.items():
            provider_count = providers.count(provider)
            if provider_count >= 3:
                best_for.append(task_type)

        return ProviderLearning(
            provider=provider,
            total_executions=ps.get("executions", 0),
            success_rate=ps.get("successes", 0) / n,
            avg_latency_ms=ps.get("total_latency", 0.0) / n,
            avg_quality=ps.get("total_quality", 0.0) / n,
            avg_cost=ps.get("total_cost", 0.0) / n,
            best_for=best_for,
        )

    def compare_providers(self) -> dict[str, ProviderLearning]:
        """Compare all providers."""
        return {
            p: self.get_provider_learning(p)
            for p in self._provider_stats
        }

    def best_provider_for(self, task_type: str = "") -> Optional[str]:
        """Find the best provider for a task type based on history."""
        providers = self._task_types.get(task_type, [])
        if not providers:
            return None

        # Count and rank by quality
        scores: dict[str, list[float]] = defaultdict(list)
        for record in self._executions:
            inferred = self._infer_task_type(record.task)
            if inferred == task_type and record.success:
                scores[record.provider].append(record.quality)

        if not scores:
            return max(set(providers), key=providers.count)

        avg_scores = {
            p: sum(s) / len(s) for p, s in scores.items()
        }
        return max(avg_scores, key=avg_scores.get)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def generate_recommendations(self) -> list[Recommendation]:
        """Generate learning-based recommendations."""
        recs: list[Recommendation] = []

        # Provider recommendations
        providers = self.compare_providers()
        sorted_providers = sorted(
            providers.items(),
            key=lambda x: x[1].avg_quality,
            reverse=True,
        )
        if sorted_providers:
            best = sorted_providers[0]
            recs.append(
                Recommendation(
                    category="provider",
                    recommendation=f"Best overall provider: {best[0]} "
                    f"(quality={best[1].avg_quality:.2f}, "
                    f"success={best[1].success_rate:.0%})",
                    confidence=min(1.0, best[1].total_executions / 50.0),
                    based_on=best[1].total_executions,
                )
            )

        # Mode recommendations
        mode_counts: dict[str, int] = defaultdict(int)
        for record in self._executions:
            if record.mode:
                mode_counts[record.mode] += 1

        if mode_counts:
            most_used = max(mode_counts, key=mode_counts.get)
            recs.append(
                Recommendation(
                    category="mode",
                    recommendation=f"Most used execution mode: {most_used}",
                    confidence=0.7,
                    based_on=mode_counts[most_used],
                )
            )

        return recs

    def suggest_optimization(self, area: str) -> list[str]:
        """Suggest optimizations for a specific area."""
        suggestions: list[str] = []

        if area == "providers":
            low_performers = [
                p for p, ps in self._provider_stats.items()
                if ps["executions"] >= 5
                and (ps["successes"] / max(1, ps["executions"])) < 0.5
            ]
            for lp in low_performers:
                suggestions.append(f"Consider reducing usage of {lp}: low success rate")

        if area == "cost":
            expensive = sorted(
                [
                    (p, ps["total_cost"] / max(1, ps["executions"]))
                    for p, ps in self._provider_stats.items()
                    if ps["executions"] > 0
                ],
                key=lambda x: x[1],
                reverse=True,
            )
            if expensive:
                suggestions.append(
                    f"Most expensive provider: {expensive[0][0]} "
                    f"(${expensive[0][1]:.4f}/call)"
                )

        if area == "quality":
            if self._executions:
                avg_q = sum(r.quality for r in self._executions) / len(self._executions)
                if avg_q < 0.5:
                    suggestions.append(
                        f"Average quality is low ({avg_q:.2f}). "
                        "Consider using higher-quality providers or modes."
                    )

        self._optimization_suggestions.extend(suggestions)
        return suggestions

    # ------------------------------------------------------------------
    # Stats & Learning Cache
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get learning engine statistics."""
        total = len(self._executions)
        successes = sum(1 for r in self._executions if r.success)
        return {
            "total_executions": total,
            "success_rate": successes / max(1, total),
            "providers_tracked": len(self._provider_stats),
            "task_types": len(self._task_types),
            "generation": self._generation,
            "has_suggestions": len(self._optimization_suggestions) > 0,
        }

    def get_learning_cache(self) -> dict[str, Any]:
        """Export the learning cache for persistence or transfer."""
        return {
            "generation": self._generation,
            "provider_stats": {
                p: dict(s) for p, s in self._provider_stats.items()
            },
            "task_types": dict(self._task_types),
            "total_executions": len(self._executions),
        }

    def evolve(self) -> None:
        """Evolve the learning engine: consolidate and generate insights."""
        self._generation += 1
        self.generate_recommendations()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_task_type(task: str) -> str:
        """Infer task type from task description."""
        task_lower = task.lower()
        keywords = {
            "summarization": ["summarize", "summary", "summarize", "tl;dr"],
            "coding": ["code", "programming", "function", "bug", "debug"],
            "question": ["what", "who", "where", "when", "why", "how"],
            "creative": ["write", "story", "poem", "creative", "design"],
            "analysis": ["analyze", "analysis", "compare", "evaluate"],
            "translation": ["translate", "translation"],
        }
        for task_type, kws in keywords.items():
            if any(kw in task_lower for kw in kws):
                return task_type
        return "general"

    def clear(self) -> None:
        """Clear all learning data."""
        self._executions.clear()
        self._provider_stats.clear()
        self._task_types.clear()
        self._optimization_suggestions.clear()
        self._generation = 0
