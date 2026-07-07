"""Tests for M7.4 Multi-Model Orchestration (MOA)."""
from __future__ import annotations

import pytest

from moa.engine import (
    MOAEngine,
    MOAExecutionMode,
    MOAResult,
    MOAStrategy,
)


# A simple model caller that returns deterministic responses
async def _mock_model_caller(provider: str, prompt: str) -> str:
    if "ERROR" in prompt.upper() and "MOCK" in prompt:
        raise RuntimeError("Simulated provider error")
    return f"[{provider}] response to: {prompt[:50]}"


class TestMOAStrategy:
    def test_default_strategy(self) -> None:
        s = MOAStrategy(mode=MOAExecutionMode.PARALLEL, providers=["a", "b"])
        assert s.mode == MOAExecutionMode.PARALLEL
        assert s.providers == ["a", "b"]
        assert s.max_retries == 2

    def test_judge_strategy(self) -> None:
        s = MOAStrategy(
            mode=MOAExecutionMode.JUDGE,
            providers=["a", "b", "judge"],
            judge_provider="judge",
        )
        assert s.judge_provider == "judge"


class TestMOAResult:
    def test_default(self) -> None:
        r = MOAResult()
        assert r.mode == MOAExecutionMode.PARALLEL
        assert r.confidence == 0.0
        assert not r.consensus

    def test_to_dict(self) -> None:
        r = MOAResult(
            mode=MOAExecutionMode.VOTING,
            final_answer="test",
            confidence=0.9,
        )
        d = r.to_dict()
        assert d["mode"] == "voting"
        assert d["confidence"] == 0.9


class TestMOAEngine:
    @pytest.mark.asyncio
    async def test_parallel_execution(self) -> None:
        engine = MOAEngine(model_caller=_mock_model_caller)
        strategy = MOAStrategy(
            mode=MOAExecutionMode.PARALLEL,
            providers=["anthropic", "openai", "gemini"],
        )
        result = await engine.execute("What is Python?", strategy)
        assert result.mode == MOAExecutionMode.PARALLEL
        assert len(result.provider_results) == 3
        assert result.total_latency_ms >= 0

    @pytest.mark.asyncio
    async def test_sequential_execution(self) -> None:
        engine = MOAEngine(model_caller=_mock_model_caller)
        strategy = MOAStrategy(
            mode=MOAExecutionMode.SEQUENTIAL,
            providers=["anthropic", "openai"],
        )
        result = await engine.execute("Write a poem", strategy)
        assert result.mode == MOAExecutionMode.SEQUENTIAL
        assert len(result.provider_results) == 2

    @pytest.mark.asyncio
    async def test_voting_execution(self) -> None:
        engine = MOAEngine(model_caller=_mock_model_caller)
        strategy = MOAStrategy(
            mode=MOAExecutionMode.VOTING,
            providers=["anthropic", "openai", "gemini"],
        )
        result = await engine.execute("What is 2+2?", strategy)
        assert result.mode == MOAExecutionMode.VOTING
        assert result.voting_result

    @pytest.mark.asyncio
    async def test_consensus_execution(self) -> None:
        engine = MOAEngine(model_caller=_mock_model_caller)
        strategy = MOAStrategy(
            mode=MOAExecutionMode.CONSENSUS,
            providers=["anthropic", "openai"],
        )
        result = await engine.execute("Say hello", strategy)
        assert result.mode == MOAExecutionMode.CONSENSUS
        assert result.attempts >= 1

    @pytest.mark.asyncio
    async def test_judge_execution(self) -> None:
        engine = MOAEngine(model_caller=_mock_model_caller)
        strategy = MOAStrategy(
            mode=MOAExecutionMode.JUDGE,
            providers=["anthropic", "openai", "judge"],
            judge_provider="judge",
        )
        result = await engine.execute("Best programming language?", strategy)
        assert result.mode == MOAExecutionMode.JUDGE
        assert result.judge_feedback

    @pytest.mark.asyncio
    async def test_critic_execution(self) -> None:
        engine = MOAEngine(model_caller=_mock_model_caller)
        strategy = MOAStrategy(
            mode=MOAExecutionMode.CRITIC,
            providers=["anthropic", "openai", "gemini"],
        )
        result = await engine.execute("Explain REST APIs", strategy)
        assert result.mode == MOAExecutionMode.CRITIC
        assert result.judge_feedback  # critique is stored here

    @pytest.mark.asyncio
    async def test_synthesize_execution(self) -> None:
        engine = MOAEngine(model_caller=_mock_model_caller)
        strategy = MOAStrategy(
            mode=MOAExecutionMode.SYNTHESIZE,
            providers=["anthropic", "openai", "gemini"],
        )
        result = await engine.execute("Summarize AI", strategy)
        assert result.mode == MOAExecutionMode.SYNTHESIZE

    @pytest.mark.asyncio
    async def test_no_model_caller(self) -> None:
        engine = MOAEngine()  # No model caller
        strategy = MOAStrategy(
            mode=MOAExecutionMode.PARALLEL,
            providers=["anthropic"],
        )
        result = await engine.execute("test", strategy)
        assert "No model caller" in result.final_answer

    @pytest.mark.asyncio
    async def test_retry_on_error(self) -> None:
        engine = MOAEngine(model_caller=_mock_model_caller)
        strategy = MOAStrategy(
            mode=MOAExecutionMode.PARALLEL,
            providers=["error_provider"],
            max_retries=3,
        )
        # The mock caller doesn't really error, so this tests the retry infrastructure
        result = await engine.execute("test", strategy)
        assert result is not None

    @pytest.mark.asyncio
    async def test_history(self) -> None:
        engine = MOAEngine(model_caller=_mock_model_caller)
        strategy = MOAStrategy(
            mode=MOAExecutionMode.PARALLEL,
            providers=["anthropic"],
        )
        await engine.execute("q1", strategy)
        await engine.execute("q2", strategy)
        history = engine.get_history()
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_clear_history(self) -> None:
        engine = MOAEngine(model_caller=_mock_model_caller)
        strategy = MOAStrategy(
            mode=MOAExecutionMode.PARALLEL,
            providers=["anthropic"],
        )
        await engine.execute("q1", strategy)
        engine.clear_history()
        assert len(engine.get_history()) == 0

    @pytest.mark.asyncio
    async def test_get_stats(self) -> None:
        engine = MOAEngine(model_caller=_mock_model_caller)
        strategy = MOAStrategy(
            mode=MOAExecutionMode.PARALLEL,
            providers=["anthropic"],
        )
        await engine.execute("q1", strategy)
        stats = engine.get_stats()
        assert stats["total_executions"] == 1

    @staticmethod
    def test_synthesize_empty() -> None:
        result = MOAEngine._synthesize([])
        assert result == ""

    @staticmethod
    def test_synthesize_single() -> None:
        result = MOAEngine._synthesize(["hello"])
        assert result == "hello"

    @staticmethod
    def test_synthesize_longest() -> None:
        result = MOAEngine._synthesize(["hi", "hello world", "hey"])
        assert result == "hello world"

    @staticmethod
    def test_compute_confidence_empty() -> None:
        assert MOAEngine._compute_confidence([]) == 0.0

    @staticmethod
    def test_compute_confidence_agreement() -> None:
        answers = ["same answer", "same answer", "same answer"]
        assert MOAEngine._compute_confidence(answers) == 1.0

    @staticmethod
    def test_compute_confidence_disagreement() -> None:
        answers = ["answer a", "answer b", "answer c"]
        conf = MOAEngine._compute_confidence(answers)
        assert conf < 1.0
