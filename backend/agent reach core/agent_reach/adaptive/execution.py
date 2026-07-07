"""
Adaptive Execution (M7.9).

Budget-aware, quality-aware execution with multiple modes:
- Fast Mode (minimum cost/latency)
- Balanced Mode (default)
- Maximum Quality Mode (best results)
- Adaptive Retry
- Dynamic Planning
- Automatic Agent Selection

Layer: Application/Core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ExecutionMode(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    MAXIMUM_QUALITY = "maximum_quality"


class AdaptiveStrategy(str, Enum):
    """How the execution adapts."""
    MIN_COST = "min_cost"
    MIN_LATENCY = "min_latency"
    MAX_QUALITY = "max_quality"
    AUTO = "auto"  # dynamic based on context


@dataclass
class ExecutionBudget:
    """Budget constraints for adaptive execution."""
    max_cost: float = float("inf")
    max_latency_ms: float = float("inf")
    max_tokens: int = 8192
    max_providers: int = 3
    mode: ExecutionMode = ExecutionMode.BALANCED


@dataclass
class ExecutionConfig:
    """Configuration for adaptive execution."""
    mode: ExecutionMode = ExecutionMode.BALANCED
    strategy: AdaptiveStrategy = AdaptiveStrategy.AUTO
    budget: ExecutionBudget = field(default_factory=ExecutionBudget)
    prefer_cheap: bool = False
    allow_fallback: bool = True
    max_retries: int = 2
    quality_threshold: float = 0.6
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdaptiveResult:
    """Result from adaptive execution."""
    mode_used: ExecutionMode = ExecutionMode.BALANCED
    provider_used: str = ""
    answer: str = ""
    quality_score: float = 0.0
    cost: float = 0.0
    latency_ms: float = 0.0
    retries: int = 0
    adapted: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class AdaptiveExecutor:
    """Adaptive execution engine.

    Selects execution mode, providers, and strategies based on:
    - Budget constraints
    - Quality requirements
    - Historical performance
    - Task characteristics
    """

    def __init__(self) -> None:
        self._history: list[AdaptiveResult] = []
        self._mode_stats: dict[ExecutionMode, dict[str, float]] = {
            m: {"count": 0, "total_cost": 0, "total_latency": 0, "avg_quality": 0}
            for m in ExecutionMode
        }

    def select_mode(
        self,
        task_complexity: float = 0.5,
        budget: Optional[ExecutionBudget] = None,
        user_preference: Optional[ExecutionMode] = None,
    ) -> ExecutionMode:
        """Select the best execution mode for a task.

        Args:
            task_complexity: 0 (simple) to 1 (very complex).
            budget: Budget constraints.
            user_preference: Explicit user preference.

        Returns:
            Recommended ExecutionMode.
        """
        if user_preference:
            return user_preference

        budget = budget or ExecutionBudget()

        if budget.mode != ExecutionMode.BALANCED:
            return budget.mode

        if task_complexity < 0.3:
            return ExecutionMode.FAST
        elif task_complexity > 0.7:
            return ExecutionMode.MAXIMUM_QUALITY
        return ExecutionMode.BALANCED

    def build_config(
        self,
        mode: ExecutionMode,
        task_complexity: float = 0.5,
        max_cost: float = float("inf"),
        max_latency_ms: float = float("inf"),
    ) -> ExecutionConfig:
        """Build an execution configuration for a mode."""
        budget = ExecutionBudget(
            max_cost=max_cost,
            max_latency_ms=max_latency_ms,
            mode=mode,
        )

        strategy = AdaptiveStrategy.AUTO
        if mode == ExecutionMode.FAST:
            strategy = AdaptiveStrategy.MIN_LATENCY
        elif mode == ExecutionMode.MAXIMUM_QUALITY:
            strategy = AdaptiveStrategy.MAX_QUALITY

        return ExecutionConfig(
            mode=mode,
            strategy=strategy,
            budget=budget,
            prefer_cheap=(mode == ExecutionMode.FAST),
            max_retries=0 if mode == ExecutionMode.FAST else 2,
            quality_threshold=0.3 if mode == ExecutionMode.FAST else 0.6,
        )

    def should_retry(
        self,
        result: AdaptiveResult,
        config: ExecutionConfig,
    ) -> bool:
        """Decide whether to retry based on result quality."""
        if result.retries >= config.max_retries:
            return False
        if result.quality_score >= config.quality_threshold:
            return False
        return True

    def select_retry_strategy(
        self,
        result: AdaptiveResult,
        config: ExecutionConfig,
    ) -> str:
        """Select a retry strategy based on what went wrong."""
        if result.quality_score < 0.3:
            return "different_provider"
        if result.latency_ms > (config.budget.max_latency_ms * 0.8):
            return "fast_provider"
        return "revised_prompt"

    # ------------------------------------------------------------------
    # History & Stats
    # ------------------------------------------------------------------

    def record_result(self, result: AdaptiveResult) -> None:
        """Record an execution result for learning."""
        self._history.append(result)
        stats = self._mode_stats[result.mode_used]
        stats["count"] += 1
        stats["total_cost"] += result.cost
        stats["total_latency"] += result.latency_ms
        if stats["count"] > 0:
            stats["avg_quality"] = (
                (stats["avg_quality"] * (stats["count"] - 1) + result.quality_score)
                / stats["count"]
            )

    def get_mode_stats(self) -> dict[str, dict[str, float]]:
        """Get statistics per execution mode."""
        result: dict[str, dict[str, float]] = {}
        for mode, stats in self._mode_stats.items():
            count = stats["count"]
            result[mode.value] = {
                "count": count,
                "avg_cost": stats["total_cost"] / max(1, count),
                "avg_latency_ms": stats["total_latency"] / max(1, count),
                "avg_quality": stats["avg_quality"],
            }
        return result

    def get_recommendation(self, task_complexity: float = 0.5) -> dict[str, Any]:
        """Get a recommendation for how to execute a task."""
        mode = self.select_mode(task_complexity)
        config = self.build_config(mode, task_complexity)
        return {
            "recommended_mode": mode.value,
            "strategy": config.strategy.value,
            "max_retries": config.max_retries,
            "quality_threshold": config.quality_threshold,
            "prefer_cheap": config.prefer_cheap,
        }

    def clear(self) -> None:
        """Clear all history."""
        self._history.clear()
        for stats in self._mode_stats.values():
            stats["count"] = 0
            stats["total_cost"] = 0
            stats["total_latency"] = 0
            stats["avg_quality"] = 0
