"""
Reflection Engine V2 (M7.5).

Enhanced reflection with self-critique, improvement suggestions,
automatic retry, execution history, and reflection memory.

Builds on the existing ReflectionEngine from Milestone 4.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from evaluation.engine import EvaluationReport
from reflection.engine import ReflectionEngine, ReflectionInsight, ReflectionReport


@dataclass
class ReflectionMemory:
    """Persistent memory of past reflections for learning."""

    id: str = ""
    timestamp: float = field(default_factory=time.time)
    context: str = ""
    insight: ReflectionInsight | None = None
    improvement: str = ""
    was_effective: bool = False


@dataclass
class V2ReflectionReport(ReflectionReport):
    """Extended reflection report with V2 features."""

    reflection_score: float = 0.0  # 0-100 overall quality
    error_detected: bool = False
    improvement_suggestions: list[str] = field(default_factory=list)
    should_auto_retry: bool = False
    retry_strategy: str = ""  # "same", "different_provider", "revised_prompt"
    improvement_applied: bool = False


class ReflectionEngineV2:
    """Enhanced reflection engine with self-improvement capabilities.

    Extends the base ReflectionEngine with:
    - Reflection scoring
    - Error detection
    - Improvement suggestions
    - Automatic retry decisions
    - Reflection memory for learning
    """

    def __init__(self) -> None:
        self._base = ReflectionEngine()
        self._memory: list[ReflectionMemory] = []
        self._reflection_count: int = 0
        self._improvement_count: int = 0
        self._retry_count: int = 0

    # ------------------------------------------------------------------
    # Core reflection
    # ------------------------------------------------------------------

    def reflect(self, evaluation_report: EvaluationReport) -> V2ReflectionReport:
        """Reflect on an evaluation report and produce enhanced insights.

        Args:
            evaluation_report: Evaluation results to reflect on.

        Returns:
            V2ReflectionReport with extended insights and recommendations.
        """
        # Get base insights
        base_report = self._base.reflect(evaluation_report)

        # Compute reflection score
        score = self._compute_reflection_score(evaluation_report)

        # Detect errors
        errors_detected = self._detect_errors(evaluation_report, base_report.insights)

        # Generate improvement suggestions
        suggestions = self._generate_improvements(evaluation_report, base_report.insights)

        # Decide on auto-retry
        auto_retry, retry_strategy = self._decide_retry(
            evaluation_report, base_report.insights, score
        )

        self._reflection_count += 1

        if auto_retry:
            self._retry_count += 1

        return V2ReflectionReport(
            insights=base_report.insights,
            summary=base_report.summary,
            should_retry=base_report.should_retry,
            reflection_score=score,
            error_detected=errors_detected,
            improvement_suggestions=suggestions,
            should_auto_retry=auto_retry,
            retry_strategy=retry_strategy,
        )

    def critique(
        self,
        output: str,
        expected: str = "",
        context: str = "",
    ) -> V2ReflectionReport:
        """Perform a self-critique of an output.

        Args:
            output: The output to critique.
            expected: Optional expected output.
            context: Additional context about the task.

        Returns:
            V2ReflectionReport with critique insights.
        """
        insights: list[ReflectionInsight] = []

        # Basic quality checks
        if not output or not output.strip():
            insights.append(
                ReflectionInsight(
                    category="completeness",
                    severity="high",
                    message="Output is empty or whitespace-only.",
                    suggestion="Regenerate with more detailed prompting.",
                )
            )

        if expected and output != expected:
            severity = "high" if len(output) < len(expected) * 0.5 else "medium"
            insights.append(
                ReflectionInsight(
                    category="accuracy",
                    severity=severity,
                    message=f"Output differs from expected. Expected {len(expected)} chars, got {len(output)}.",
                    suggestion="Review the task requirements and regenerate.",
                )
            )

        # Length-based quality heuristics
        if output and len(output) < 50:
            insights.append(
                ReflectionInsight(
                    category="completeness",
                    severity="medium",
                    message="Output is very short; may be incomplete.",
                    suggestion="Consider asking for a more detailed response.",
                )
            )

        # Repetition detection
        if output and len(set(output.lower().split())) < len(output.split()) * 0.3:
            insights.append(
                ReflectionInsight(
                    category="quality",
                    severity="low",
                    message="Output may contain repetitive content.",
                    suggestion="Adjust temperature or request more varied output.",
                )
            )

        score = 100.0
        for i in insights:
            if i.severity == "high":
                score -= 30
            elif i.severity == "medium":
                score -= 15
            else:
                score -= 5
        score = max(0.0, score)

        auto_retry = any(i.severity == "high" for i in insights)
        strategy = "revised_prompt" if auto_retry else ""

        return V2ReflectionReport(
            insights=insights,
            summary=f"Self-critique: {len(insights)} issues found.",
            should_retry=auto_retry,
            reflection_score=score,
            error_detected=any(i.severity == "high" for i in insights),
            improvement_suggestions=[i.suggestion for i in insights if i.suggestion],
            should_auto_retry=auto_retry,
            retry_strategy=strategy,
        )

    # ------------------------------------------------------------------
    # Improvement tracking
    # ------------------------------------------------------------------

    def record_improvement(
        self,
        context: str,
        insight: ReflectionInsight,
        improvement: str,
        was_effective: bool = True,
    ) -> None:
        """Record an improvement for future learning."""
        mem = ReflectionMemory(
            context=context,
            insight=insight,
            improvement=improvement,
            was_effective=was_effective,
        )
        self._memory.append(mem)
        if was_effective:
            self._improvement_count += 1

    def get_effective_improvements(self) -> list[ReflectionMemory]:
        """Get all recorded effective improvements."""
        return [m for m in self._memory if m.was_effective]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_reflection_score(report: EvaluationReport) -> float:
        """Compute an overall reflection quality score (0-100)."""
        if not report.results:
            return 50.0
        return report.overall_score * 100.0

    @staticmethod
    def _detect_errors(
        report: EvaluationReport,
        insights: list[ReflectionInsight],
    ) -> bool:
        """Detect if there are real errors (not just quality issues)."""
        if not report.overall_passed:
            return True
        return any(i.severity == "high" for i in insights)

    @staticmethod
    def _generate_improvements(
        report: EvaluationReport,
        insights: list[ReflectionInsight],
    ) -> list[str]:
        """Generate improvement suggestions from insights."""
        suggestions: list[str] = []
        for insight in insights:
            if insight.suggestion:
                suggestions.append(insight.suggestion)
        if not report.overall_passed and not suggestions:
            suggestions.append(
                "Review execution output, adjust parameters, and retry."
            )
        return suggestions

    @staticmethod
    def _decide_retry(
        report: EvaluationReport,
        insights: list[ReflectionInsight],
        score: float,
    ) -> tuple[bool, str]:
        """Decide whether to auto-retry and with what strategy."""
        if score >= 80:
            return False, ""

        if score < 30:
            return True, "different_provider"
        elif score < 60:
            return True, "revised_prompt"
        elif not report.overall_passed:
            return True, "same"

        return False, ""

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get reflection engine statistics."""
        return {
            "total_reflections": self._reflection_count,
            "total_improvements": self._improvement_count,
            "total_retries": self._retry_count,
            "memory_entries": len(self._memory),
            "effective_rate": (
                self._improvement_count / max(1, len(self._memory))
            ),
        }

    def clear(self) -> None:
        """Reset all state."""
        self._base.clear()
        self._memory.clear()
        self._reflection_count = 0
        self._improvement_count = 0
        self._retry_count = 0
