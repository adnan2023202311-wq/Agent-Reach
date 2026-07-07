"""Tests for Evaluation Engine (M4.8)."""

from __future__ import annotations

import pytest

from evaluation.engine import EvaluationCriteria, EvaluationEngine, EvaluationResult


def _exact_match_evaluator(output: str, expected: str, **kwargs: object) -> float:
    return 1.0 if output == expected else 0.0


def _length_evaluator(output: str, **kwargs: object) -> float:
    return min(1.0, len(output) / 100.0)


class TestEvaluationEngine:
    def test_register_and_list(self) -> None:
        engine = EvaluationEngine()
        criteria = EvaluationCriteria(name="exact", evaluator=_exact_match_evaluator)
        engine.register_criteria(criteria)
        assert len(engine.list_criteria()) == 1
        assert engine.list_criteria()[0].name == "exact"

    def test_unregister(self) -> None:
        engine = EvaluationEngine()
        engine.register_criteria(EvaluationCriteria(name="x", evaluator=_exact_match_evaluator))
        assert engine.unregister_criteria("x") is True
        assert engine.unregister_criteria("x") is False

    def test_evaluate_exact_match_pass(self) -> None:
        engine = EvaluationEngine()
        engine.register_criteria(
            EvaluationCriteria(name="exact", evaluator=_exact_match_evaluator, threshold=1.0)
        )
        report = engine.evaluate(output="hello", expected="hello")
        assert report.overall_passed is True
        assert report.overall_score == 1.0
        assert report.results[0].passed is True

    def test_evaluate_exact_match_fail(self) -> None:
        engine = EvaluationEngine()
        engine.register_criteria(
            EvaluationCriteria(name="exact", evaluator=_exact_match_evaluator, threshold=1.0)
        )
        report = engine.evaluate(output="hello", expected="world")
        assert report.overall_passed is False
        assert report.overall_score == 0.0
        assert report.results[0].passed is False

    def test_evaluate_multiple_criteria(self) -> None:
        engine = EvaluationEngine()
        engine.register_criteria(
            EvaluationCriteria(name="exact", weight=0.7, evaluator=_exact_match_evaluator)
        )
        engine.register_criteria(
            EvaluationCriteria(name="length", weight=0.3, evaluator=_length_evaluator, threshold=0.05)
        )
        report = engine.evaluate(output="hello world", expected="hello world")
        assert report.overall_passed is True
        assert report.overall_score == pytest.approx(1.0 * 0.7 + 0.11 * 0.3, abs=0.01)

    def test_evaluate_selective_criteria(self) -> None:
        engine = EvaluationEngine()
        engine.register_criteria(EvaluationCriteria(name="a", evaluator=lambda **k: 1.0))
        engine.register_criteria(EvaluationCriteria(name="b", evaluator=lambda **k: 0.0))
        report = engine.evaluate(output="", criteria_names=["a"])
        assert len(report.results) == 1
        assert report.results[0].criterion_name == "a"

    def test_evaluator_exception_handling(self) -> None:
        engine = EvaluationEngine()
        engine.register_criteria(
            EvaluationCriteria(name="bad", evaluator=lambda **k: 1 / 0)
        )
        report = engine.evaluate(output="")
        assert report.results[0].score == 0.0
        assert "Evaluator failed" in report.results[0].feedback

    def test_score_clamping(self) -> None:
        engine = EvaluationEngine()
        engine.register_criteria(
            EvaluationCriteria(name="high", evaluator=lambda **k: 5.0)
        )
        report = engine.evaluate(output="")
        assert report.results[0].score == 1.0

    def test_empty_report(self) -> None:
        engine = EvaluationEngine()
        report = engine.evaluate(output="")
        assert report.overall_score == 0.0
        assert report.overall_passed is False

    def test_clear(self) -> None:
        engine = EvaluationEngine()
        engine.register_criteria(EvaluationCriteria(name="x", evaluator=_exact_match_evaluator))
        engine.clear()
        assert engine.list_criteria() == []
