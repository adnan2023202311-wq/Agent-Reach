"""
Evaluation Engine for Milestone 4.

Per ADR-002: Evaluation ALWAYS happens before Reflection.
Reflection consumes evaluation results. Reflection never replaces evaluation.

Inspired by DeepEval's evaluation metrics, but built natively without
library dependencies.

Provides:
- EvaluationCriteria: defines what to evaluate
- EvaluationResult: score, pass/fail, feedback
- EvaluationEngine: evaluates execution results against criteria

Layer: Application/Core — depends inward on domain/ and infrastructure/ only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class EvaluationCriteria:
    """A criterion against which execution results are evaluated."""

    name: str
    description: str = ""
    weight: float = 1.0
    threshold: float = 0.5  # minimum score to pass
    evaluator: Callable[..., float] = field(default=lambda **kwargs: 0.0)


@dataclass
class EvaluationResult:
    """Outcome of evaluating one criterion."""

    criterion_name: str
    score: float  # 0.0 to 1.0
    passed: bool
    feedback: str = ""
    weight: float = 1.0


@dataclass
class EvaluationReport:
    """Aggregated results from evaluating multiple criteria."""

    results: list[EvaluationResult] = field(default_factory=list)
    overall_score: float = 0.0
    overall_passed: bool = False

    def __post_init__(self) -> None:
        if self.results:
            total_weight = sum(r.weight for r in self.results)
            if total_weight > 0:
                self.overall_score = sum(r.score * r.weight for r in self.results) / total_weight
            self.overall_passed = all(r.passed for r in self.results)


class EvaluationEngine:
    """Evaluates execution results against a set of criteria.

    The EvaluationEngine is mandatory in the execution pipeline.
    No reflection may occur without prior evaluation.
    """

    def __init__(self) -> None:
        self._criteria: dict[str, EvaluationCriteria] = {}

    def register_criteria(self, criteria: EvaluationCriteria) -> None:
        """Register an evaluation criterion."""
        self._criteria[criteria.name] = criteria

    def unregister_criteria(self, name: str) -> bool:
        """Remove a criterion."""
        if name not in self._criteria:
            return False
        del self._criteria[name]
        return True

    def list_criteria(self) -> list[EvaluationCriteria]:
        """List all registered criteria."""
        return list(self._criteria.values())

    def evaluate(
        self,
        output: Any,
        expected: Any | None = None,
        criteria_names: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> EvaluationReport:
        """Evaluate an execution result against registered criteria.

        Args:
            output: The actual execution output
            expected: Optional expected output for comparison
            criteria_names: Specific criteria to evaluate (all if None)
            context: Additional context for evaluators

        Returns:
            EvaluationReport with per-criterion and overall scores
        """
        results: list[EvaluationResult] = []
        to_evaluate = criteria_names or list(self._criteria.keys())
        ctx = context or {}

        for name in to_evaluate:
            criterion = self._criteria.get(name)
            if criterion is None:
                continue

            try:
                score = criterion.evaluator(
                    output=output,
                    expected=expected,
                    **ctx,
                )
                # Clamp score to [0, 1]
                score = max(0.0, min(1.0, float(score)))
            except Exception as exc:
                score = 0.0
                feedback = f"Evaluator failed: {exc}"
            else:
                feedback = "Passed" if score >= criterion.threshold else "Below threshold"

            results.append(
                EvaluationResult(
                    criterion_name=name,
                    score=score,
                    passed=score >= criterion.threshold,
                    feedback=feedback,
                    weight=criterion.weight,
                )
            )

        return EvaluationReport(results=results)

    def clear(self) -> None:
        """Remove all criteria. Useful for testing."""
        self._criteria.clear()
