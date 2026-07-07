"""
Reflection Engine for Milestone 4.

Per ADR-002: Reflection consumes evaluation results. Reflection never
replaces evaluation.

Inspired by Claude Code's incremental engineering workflow and
self-improvement concepts, but built natively.

Provides:
- ReflectionInsight: a single actionable insight
- ReflectionReport: aggregated insights from reflection
- ReflectionEngine: consumes EvaluationReport and produces insights

Layer: Application/Core — depends inward on domain/ and infrastructure/ only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from evaluation.engine import EvaluationReport, EvaluationResult


@dataclass
class ReflectionInsight:
    """A single actionable insight produced by reflection."""

    category: str  # e.g., "accuracy", "completeness", "performance"
    severity: str  # "low", "medium", "high"
    message: str
    suggestion: str = ""
    related_criterion: str = ""


@dataclass
class ReflectionReport:
    """Aggregated insights from reflecting on an evaluation."""

    insights: list[ReflectionInsight] = field(default_factory=list)
    summary: str = ""
    should_retry: bool = False


class ReflectionEngine:
    """Generates insights by consuming evaluation results.

    The ReflectionEngine MUST NOT evaluate on its own — it only
    interprets EvaluationReports produced by the EvaluationEngine.
    """

    def __init__(self) -> None:
        self._strategies: dict[str, Callable[[EvaluationResult], list[ReflectionInsight]]] = {}
        self._register_default_strategies()

    def _register_default_strategies(self) -> None:
        """Register built-in reflection strategies."""
        self._strategies["default"] = self._default_reflection

    def register_strategy(
        self,
        name: str,
        strategy: Callable[[EvaluationResult], list[ReflectionInsight]],
    ) -> None:
        """Register a custom reflection strategy."""
        self._strategies[name] = strategy

    def reflect(self, evaluation_report: EvaluationReport) -> ReflectionReport:
        """Consume an EvaluationReport and produce a ReflectionReport.

        Args:
            evaluation_report: The evaluation results to reflect on

        Returns:
            ReflectionReport with insights and recommendations
        """
        insights: list[ReflectionInsight] = []

        for result in evaluation_report.results:
            strategy = self._strategies.get("default")
            if strategy is not None:
                insights.extend(strategy(result))

        should_retry = any(i.severity == "high" for i in insights) or not evaluation_report.overall_passed

        summary = self._generate_summary(evaluation_report, insights)

        return ReflectionReport(
            insights=insights,
            summary=summary,
            should_retry=should_retry,
        )

    @staticmethod
    def _default_reflection(result: EvaluationResult) -> list[ReflectionInsight]:
        """Default strategy: produce insights based on score and threshold."""
        insights: list[ReflectionInsight] = []

        if not result.passed:
            severity = "high" if result.score < 0.3 else "medium"
            insights.append(
                ReflectionInsight(
                    category=result.criterion_name,
                    severity=severity,
                    message=f"Criterion '{result.criterion_name}' failed with score {result.score:.2f}",
                    suggestion="Review execution output and adjust parameters or logic.",
                    related_criterion=result.criterion_name,
                )
            )
        elif result.score < 0.8:
            insights.append(
                ReflectionInsight(
                    category=result.criterion_name,
                    severity="low",
                    message=f"Criterion '{result.criterion_name}' passed but score is only {result.score:.2f}",
                    suggestion="Consider optimizing for higher quality output.",
                    related_criterion=result.criterion_name,
                )
            )

        return insights

    @staticmethod
    def _generate_summary(
        evaluation_report: EvaluationReport,
        insights: list[ReflectionInsight],
    ) -> str:
        """Generate a human-readable summary."""
        if evaluation_report.overall_passed and not insights:
            return "All criteria passed with satisfactory scores."

        parts = []
        if not evaluation_report.overall_passed:
            parts.append("Evaluation failed overall.")
        failed = [i for i in insights if i.severity == "high"]
        if failed:
            parts.append(f"{len(failed)} high-severity issue(s) found.")
        warnings = [i for i in insights if i.severity == "medium"]
        if warnings:
            parts.append(f"{len(warnings)} medium-severity issue(s) found.")
        return " ".join(parts) if parts else "Evaluation passed with minor observations."

    def clear(self) -> None:
        """Reset to default strategies. Useful for testing."""
        self._strategies.clear()
        self._register_default_strategies()
