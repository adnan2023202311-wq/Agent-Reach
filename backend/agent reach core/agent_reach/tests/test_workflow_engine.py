"""Tests for Workflow Engine (M4.12)."""

from __future__ import annotations

import pytest

from core.capability_resolver import CapabilityResolver
from evaluation.engine import EvaluationCriteria, EvaluationEngine
from reflection.engine import ReflectionEngine
from workflow.engine import WorkflowCheckpoint, WorkflowEngine, WorkflowState, WorkflowStep


async def _add_executor(a: int = 0, b: int = 0) -> int:
    return a + b


async def _fail_executor() -> None:
    raise RuntimeError("intentional")


class TestWorkflowEngine:
    @pytest.fixture
    def resolver(self) -> CapabilityResolver:
        r = CapabilityResolver()
        r.register("add", _add_executor)
        r.register("fail", _fail_executor)
        return r

    @pytest.fixture
    def engine(self, resolver: CapabilityResolver) -> WorkflowEngine:
        return WorkflowEngine(capability_resolver=resolver)

    @pytest.mark.asyncio
    async def test_run_single_step(self, engine: WorkflowEngine) -> None:
        steps = [WorkflowStep(step_id="s1", name="add", capability_id="add", inputs={"a": 2, "b": 3})]
        result = await engine.run("wf1", steps)
        assert result.state == WorkflowState.COMPLETED
        assert result.step_outcomes["s1"].success is True
        assert result.step_outcomes["s1"].output == 5

    @pytest.mark.asyncio
    async def test_run_sequential_steps(self, engine: WorkflowEngine) -> None:
        steps = [
            WorkflowStep(step_id="s1", capability_id="add", inputs={"a": 1, "b": 1}),
            WorkflowStep(step_id="s2", capability_id="add", inputs={"a": 2, "b": 2}, depends_on=["s1"]),
        ]
        result = await engine.run("wf1", steps)
        assert result.state == WorkflowState.COMPLETED
        assert result.step_outcomes["s1"].output == 2
        assert result.step_outcomes["s2"].output == 4

    @pytest.mark.asyncio
    async def test_run_parallel_steps(self, engine: WorkflowEngine) -> None:
        steps = [
            WorkflowStep(step_id="s1", capability_id="add", inputs={"a": 1, "b": 1}),
            WorkflowStep(step_id="s2", capability_id="add", inputs={"a": 2, "b": 2}),
        ]
        result = await engine.run("wf1", steps)
        assert result.state == WorkflowState.COMPLETED
        assert result.step_outcomes["s1"].output == 2
        assert result.step_outcomes["s2"].output == 4

    @pytest.mark.asyncio
    async def test_run_failure(self, engine: WorkflowEngine) -> None:
        steps = [WorkflowStep(step_id="s1", capability_id="fail")]
        result = await engine.run("wf1", steps)
        assert result.state == WorkflowState.FAILED
        assert result.step_outcomes["s1"].success is False
        assert "intentional" in result.step_outcomes["s1"].error

    @pytest.mark.asyncio
    async def test_run_circular_dependency(self, engine: WorkflowEngine) -> None:
        steps = [
            WorkflowStep(step_id="s1", capability_id="add", depends_on=["s2"]),
            WorkflowStep(step_id="s2", capability_id="add", depends_on=["s1"]),
        ]
        result = await engine.run("wf1", steps)
        assert result.state == WorkflowState.FAILED
        assert "Circular" in result.error

    @pytest.mark.asyncio
    async def test_checkpoint_and_resume(self, engine: WorkflowEngine) -> None:
        steps = [
            WorkflowStep(step_id="s1", capability_id="add", inputs={"a": 1, "b": 1}),
            WorkflowStep(step_id="s2", capability_id="add", inputs={"a": 2, "b": 2}, depends_on=["s1"]),
        ]
        # First run only s1
        result = await engine.run("wf1", steps)
        checkpoint = engine.create_checkpoint("wf1", result.state, result.step_outcomes)
        assert checkpoint.completed_steps == ["s1", "s2"]

        # Resume from checkpoint with additional steps
        steps2 = [
            WorkflowStep(step_id="s3", capability_id="add", inputs={"a": 3, "b": 3}, depends_on=["s2"]),
        ]
        result2 = await engine.run("wf2", steps2, resume_from=checkpoint)
        assert "s1" in result2.step_outcomes
        assert "s3" in result2.step_outcomes

    @pytest.mark.asyncio
    async def test_evaluation_integration(self, resolver: CapabilityResolver) -> None:
        eval_engine = EvaluationEngine()
        eval_engine.register_criteria(
            EvaluationCriteria(name="exact", evaluator=lambda output, expected, **k: 1.0 if output == expected else 0.0)
        )
        engine = WorkflowEngine(
            capability_resolver=resolver,
            evaluation_engine=eval_engine,
        )
        steps = [
            WorkflowStep(step_id="s1", capability_id="add", inputs={"a": 2, "b": 3}, evaluate=True),
        ]
        result = await engine.run("wf1", steps)
        assert result.step_outcomes["s1"].evaluation is not None
        assert result.step_outcomes["s1"].evaluation.overall_score == 0.0  # no expected provided

    @pytest.mark.asyncio
    async def test_reflection_integration(self, resolver: CapabilityResolver) -> None:
        eval_engine = EvaluationEngine()
        eval_engine.register_criteria(
            EvaluationCriteria(name="exact", evaluator=lambda output, expected, **k: 1.0 if output == expected else 0.0)
        )
        refl_engine = ReflectionEngine()
        engine = WorkflowEngine(
            capability_resolver=resolver,
            evaluation_engine=eval_engine,
            reflection_engine=refl_engine,
        )
        steps = [
            WorkflowStep(step_id="s1", capability_id="add", inputs={"a": 2, "b": 3}, evaluate=True, reflect=True),
        ]
        result = await engine.run("wf1", steps)
        assert result.step_outcomes["s1"].reflection is not None

    def test_get_result(self, engine: WorkflowEngine) -> None:
        assert engine.get_result("missing") is None

    def test_list_workflows(self, engine: WorkflowEngine) -> None:
        assert engine.list_workflows() == []

    def test_clear(self, engine: WorkflowEngine) -> None:
        engine.clear()
        assert engine.list_workflows() == []
