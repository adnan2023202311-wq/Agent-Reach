"""Tests for Execution Engine Improvements (M4.10)."""

from __future__ import annotations

import pytest

from core.capability_resolver import CapabilityResolver
from core.execution import ExecutionOrchestrator, ExecutionStep
from observability.tracing import SpanStatus


async def _add_executor(a: int = 0, b: int = 0) -> int:
    return a + b


async def _fail_executor() -> None:
    raise RuntimeError("intentional")


class TestExecutionOrchestrator:
    @pytest.mark.asyncio
    async def test_execute_step_success(self) -> None:
        resolver = CapabilityResolver()
        resolver.register("add", _add_executor)
        orchestrator = ExecutionOrchestrator(resolver)
        step = ExecutionStep(step_id="s1", capability_id="add", inputs={"a": 2, "b": 3})
        outcome = await orchestrator.execute_step(step)
        assert outcome.success is True
        assert outcome.output == 5
        assert outcome.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_step_unresolved(self) -> None:
        resolver = CapabilityResolver()
        orchestrator = ExecutionOrchestrator(resolver)
        step = ExecutionStep(step_id="s1", capability_id="missing")
        outcome = await orchestrator.execute_step(step)
        assert outcome.success is False
        assert "could not be resolved" in outcome.error

    @pytest.mark.asyncio
    async def test_execute_step_exception_isolation(self) -> None:
        resolver = CapabilityResolver()
        resolver.register("fail", _fail_executor)
        orchestrator = ExecutionOrchestrator(resolver)
        step = ExecutionStep(step_id="s1", capability_id="fail")
        outcome = await orchestrator.execute_step(step)
        assert outcome.success is False
        assert "intentional" in outcome.error

    @pytest.mark.asyncio
    async def test_execute_batch_sequential(self) -> None:
        resolver = CapabilityResolver()
        resolver.register("add", _add_executor)
        orchestrator = ExecutionOrchestrator(resolver)
        steps = [
            ExecutionStep(step_id="s1", capability_id="add", inputs={"a": 1, "b": 1}),
            ExecutionStep(step_id="s2", capability_id="add", inputs={"a": 2, "b": 2}, depends_on=["s1"]),
        ]
        outcomes = await orchestrator.execute_batch(steps)
        assert len(outcomes) == 2
        assert outcomes[0].output == 2
        assert outcomes[1].output == 4

    @pytest.mark.asyncio
    async def test_execute_batch_parallel(self) -> None:
        resolver = CapabilityResolver()
        resolver.register("add", _add_executor)
        orchestrator = ExecutionOrchestrator(resolver)
        steps = [
            ExecutionStep(step_id="s1", capability_id="add", inputs={"a": 1, "b": 1}),
            ExecutionStep(step_id="s2", capability_id="add", inputs={"a": 2, "b": 2}),
        ]
        outcomes = await orchestrator.execute_batch(steps)
        assert len(outcomes) == 2
        assert outcomes[0].output == 2
        assert outcomes[1].output == 4

    @pytest.mark.asyncio
    async def test_execute_batch_circular_dependency(self) -> None:
        resolver = CapabilityResolver()
        orchestrator = ExecutionOrchestrator(resolver)
        steps = [
            ExecutionStep(step_id="s1", capability_id="add", depends_on=["s2"]),
            ExecutionStep(step_id="s2", capability_id="add", depends_on=["s1"]),
        ]
        outcomes = await orchestrator.execute_batch(steps)
        assert outcomes[0].success is False
        assert "Dependency" in outcomes[0].error

    @pytest.mark.asyncio
    async def test_tracing_created(self) -> None:
        resolver = CapabilityResolver()
        resolver.register("add", _add_executor)
        orchestrator = ExecutionOrchestrator(resolver)
        step = ExecutionStep(step_id="s1", capability_id="add", inputs={"a": 1, "b": 1})
        await orchestrator.execute_step(step)
        traces = orchestrator.observability.list_traces()
        assert len(traces) == 1
        assert len(traces[0].spans) == 1

    @pytest.mark.asyncio
    async def test_tracing_error_status(self) -> None:
        resolver = CapabilityResolver()
        resolver.register("fail", _fail_executor)
        orchestrator = ExecutionOrchestrator(resolver)
        step = ExecutionStep(step_id="s1", capability_id="fail")
        await orchestrator.execute_step(step)
        traces = orchestrator.observability.list_traces()
        span = list(traces[0].spans.values())[0]
        assert span.status == SpanStatus.ERROR

    def test_clear(self) -> None:
        resolver = CapabilityResolver()
        orchestrator = ExecutionOrchestrator(resolver)
        orchestrator.clear()
        assert orchestrator.observability.list_traces() == []
