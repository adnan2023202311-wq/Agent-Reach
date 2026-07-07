"""Tests for Reflection Engine (M4.9)."""

from __future__ import annotations

import pytest

from evaluation.engine import EvaluationReport, EvaluationResult
from reflection.engine import ReflectionEngine, ReflectionInsight


class TestReflectionEngine:
    def test_reflect_all_passed(self) -> None:
        engine = ReflectionEngine()
        report = EvaluationReport(
            results=[
                EvaluationResult(criterion_name="exact", score=1.0, passed=True, weight=1.0),
            ]
        )
        reflection = engine.reflect(report)
        assert reflection.should_retry is False
        assert "passed with satisfactory scores" in reflection.summary

    def test_reflect_failed_high_severity(self) -> None:
        engine = ReflectionEngine()
        report = EvaluationReport(
            results=[
                EvaluationResult(criterion_name="exact", score=0.1, passed=False, weight=1.0),
            ]
        )
        reflection = engine.reflect(report)
        assert reflection.should_retry is True
        assert len(reflection.insights) == 1
        assert reflection.insights[0].severity == "high"
        assert "failed" in reflection.insights[0].message

    def test_reflect_failed_medium_severity(self) -> None:
        engine = ReflectionEngine()
        report = EvaluationReport(
            results=[
                EvaluationResult(criterion_name="exact", score=0.4, passed=False, weight=1.0),
            ]
        )
        reflection = engine.reflect(report)
        assert reflection.insights[0].severity == "medium"

    def test_reflect_low_score_passed(self) -> None:
        engine = ReflectionEngine()
        report = EvaluationReport(
            results=[
                EvaluationResult(criterion_name="exact", score=0.6, passed=True, weight=1.0),
            ]
        )
        reflection = engine.reflect(report)
        assert reflection.should_retry is False
        assert len(reflection.insights) == 1
        assert reflection.insights[0].severity == "low"

    def test_reflect_multiple_results(self) -> None:
        engine = ReflectionEngine()
        report = EvaluationReport(
            results=[
                EvaluationResult(criterion_name="a", score=1.0, passed=True, weight=1.0),
                EvaluationResult(criterion_name="b", score=0.2, passed=False, weight=1.0),
            ]
        )
        reflection = engine.reflect(report)
        assert len(reflection.insights) == 1
        assert reflection.insights[0].related_criterion == "b"
        assert reflection.should_retry is True

    def test_custom_strategy(self) -> None:
        engine = ReflectionEngine()

        def custom_strategy(result: EvaluationResult) -> list[ReflectionInsight]:
            return [
                ReflectionInsight(
                    category="custom",
                    severity="low",
                    message="Custom insight",
                    related_criterion=result.criterion_name,
                )
            ]

        engine.register_strategy("custom", custom_strategy)
        report = EvaluationReport(
            results=[EvaluationResult(criterion_name="x", score=1.0, passed=True, weight=1.0)]
        )
        # default strategy still runs because we didn't replace it
        reflection = engine.reflect(report)
        # default strategy produces no insight for perfect score
        assert len(reflection.insights) == 0

    def test_clear(self) -> None:
        engine = ReflectionEngine()
        engine.clear()
        report = EvaluationReport(results=[])
        reflection = engine.reflect(report)
        assert reflection.insights == []
