"""Unit tests for Workflow Models (M5.1)."""

from __future__ import annotations

import pytest

from domain.models import RetryPolicy
from workflows.models import (
    Condition,
    ConditionOp,
    StepExecutionRecord,
    StepType,
    Workflow,
    WorkflowContext,
    WorkflowResult,
    WorkflowState,
    WorkflowStep,
)


class TestStepType:
    def test_enum_values(self) -> None:
        assert StepType.AGENT.value == "agent"
        assert StepType.TOOL.value == "tool"

    def test_from_string(self) -> None:
        assert StepType("agent") is StepType.AGENT
        assert StepType("tool") is StepType.TOOL

    def test_invalid_value(self) -> None:
        with pytest.raises(ValueError):
            StepType("invalid")


class TestWorkflowState:
    def test_enum_values(self) -> None:
        assert WorkflowState.PENDING.value == "pending"
        assert WorkflowState.RUNNING.value == "running"
        assert WorkflowState.COMPLETED.value == "completed"
        assert WorkflowState.FAILED.value == "failed"
        assert WorkflowState.CANCELLED.value == "cancelled"


class TestCondition:
    def test_to_dict(self) -> None:
        c = Condition(variable="variables.x", op=ConditionOp.EQ, value=5)
        assert c.to_dict() == {"variable": "variables.x", "op": "==", "value": 5}

    def test_from_dict_roundtrip(self) -> None:
        original = Condition(variable="outputs.s1.text", op=ConditionOp.TRUTHY)
        data = original.to_dict()
        restored = Condition.from_dict(data)
        assert restored.variable == original.variable
        assert restored.op == original.op
        assert restored.value == original.value

    def test_from_dict_invalid_type(self) -> None:
        with pytest.raises(ValueError, match="must be a dict"):
            Condition.from_dict("not a dict")  # type: ignore[arg-type]

    def test_from_dict_missing_key(self) -> None:
        with pytest.raises(ValueError, match="missing required key"):
            Condition.from_dict({"op": "=="})

    def test_from_dict_unknown_op(self) -> None:
        with pytest.raises(ValueError, match="Unknown ConditionOp"):
            Condition.from_dict({"variable": "x", "op": "???"})

    def test_frozen(self) -> None:
        c = Condition(variable="x", op=ConditionOp.EQ)
        with pytest.raises((AttributeError, Exception)):
            c.variable = "y"  # type: ignore[misc]


class TestWorkflowStep:
    def test_defaults(self) -> None:
        s = WorkflowStep()
        assert s.step_id  # auto-generated
        assert s.name == ""
        assert s.type == StepType.AGENT
        assert s.target == ""
        assert s.inputs == {}
        assert s.condition is None
        assert s.depends_on == []
        assert s.retry_policy is None
        assert s.output_keys == []
        assert s.timeout_seconds == 30.0

    def test_to_dict_with_condition(self) -> None:
        s = WorkflowStep(
            step_id="s1",
            name="research",
            type=StepType.AGENT,
            target="research",
            inputs={"query": "hello"},
            condition=Condition(variable="variables.flag", op=ConditionOp.EQ, value=True),
            depends_on=["s0"],
            retry_policy=RetryPolicy(max_attempts=2),
            output_keys=["text"],
            timeout_seconds=10.0,
        )
        d = s.to_dict()
        assert d["step_id"] == "s1"
        assert d["type"] == "agent"
        assert d["target"] == "research"
        assert d["condition"]["op"] == "=="
        assert d["retry_policy"]["max_attempts"] == 2

    def test_from_dict_roundtrip(self) -> None:
        original = WorkflowStep(
            step_id="x",
            name="X",
            type=StepType.TOOL,
            target="calculator",
            inputs={"a": 1, "b": 2},
            condition=Condition("variables.go", ConditionOp.TRUTHY),
            depends_on=["a"],
            output_keys=["sum"],
        )
        d = original.to_dict()
        restored = WorkflowStep.from_dict(d)
        assert restored.step_id == original.step_id
        assert restored.name == original.name
        assert restored.type == original.type
        assert restored.target == original.target
        assert restored.inputs == original.inputs
        assert restored.condition is not None
        assert restored.condition.variable == "variables.go"
        assert restored.condition.op == ConditionOp.TRUTHY
        assert restored.depends_on == original.depends_on
        assert restored.output_keys == original.output_keys

    def test_from_dict_invalid_type(self) -> None:
        with pytest.raises(ValueError):
            WorkflowStep.from_dict({"type": "bogus"})

    def test_from_dict_no_type_defaults_to_agent(self) -> None:
        s = WorkflowStep.from_dict({"step_id": "x"})
        assert s.type == StepType.AGENT


class TestWorkflow:
    def test_defaults(self) -> None:
        w = Workflow()
        assert w.workflow_id
        assert w.name == ""
        assert w.steps == []
        assert w.variables == {}
        assert w.outputs == {}
        assert w.default_retry_policy is None
        assert w.version == "1.0"

    def test_to_dict_includes_steps(self) -> None:
        w = Workflow(
            workflow_id="wf-1",
            name="greet",
            description="a workflow",
            variables={"name": "world"},
            steps=[
                WorkflowStep(step_id="s1", type=StepType.AGENT, target="research"),
            ],
            outputs={"greeting": "outputs.s1.text"},
            metadata={"owner": "test"},
        )
        d = w.to_dict()
        assert d["workflow_id"] == "wf-1"
        assert d["name"] == "greet"
        assert d["variables"] == {"name": "world"}
        assert len(d["steps"]) == 1
        assert d["steps"][0]["step_id"] == "s1"
        assert d["outputs"] == {"greeting": "outputs.s1.text"}
        assert d["metadata"] == {"owner": "test"}

    def test_from_dict_roundtrip(self) -> None:
        original = Workflow(
            workflow_id="wf-1",
            name="greet",
            description="a workflow",
            metadata={"k": "v"},
            variables={"name": "world"},
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.AGENT,
                    target="research",
                    inputs={"query": "{{ variables.name }}"},
                ),
            ],
            outputs={"greeting": "outputs.s1.text"},
            default_retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
        )
        d = original.to_dict()
        restored = Workflow.from_dict(d)
        assert restored.workflow_id == original.workflow_id
        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.metadata == original.metadata
        assert restored.variables == original.variables
        assert len(restored.steps) == 1
        assert restored.steps[0].step_id == "s1"
        assert restored.steps[0].inputs == {"query": "{{ variables.name }}"}
        assert restored.outputs == original.outputs
        assert restored.default_retry_policy is not None
        assert restored.default_retry_policy.max_attempts == 1

    def test_from_dict_invalid_type(self) -> None:
        with pytest.raises(ValueError):
            Workflow.from_dict("not a dict")  # type: ignore[arg-type]


class TestWorkflowContext:
    def test_empty(self) -> None:
        ctx = WorkflowContext(workflow_id="wf-1")
        assert ctx.workflow_id == "wf-1"
        assert ctx.variables == {}
        assert ctx.step_outputs == {}
        assert ctx.history == []

    def test_history_accumulates(self) -> None:
        ctx = WorkflowContext(workflow_id="wf-1")
        rec = StepExecutionRecord(
            step_id="s1",
            step_name="S1",
            step_type=StepType.AGENT,
            started_at=0.0,
            finished_at=0.1,
            duration_ms=100.0,
            success=True,
        )
        ctx.history.append(rec)
        assert ctx.history[0].step_id == "s1"


class TestStepExecutionRecord:
    def test_defaults(self) -> None:
        rec = StepExecutionRecord(
            step_id="s1",
            step_name="S1",
            step_type=StepType.AGENT,
            started_at=0.0,
            finished_at=0.0,
            duration_ms=0.0,
            success=True,
        )
        assert rec.attempts == 1
        assert rec.skipped is False
        assert rec.error is None


class TestWorkflowResult:
    def test_defaults(self) -> None:
        r = WorkflowResult(workflow_id="wf-1", state=WorkflowState.COMPLETED)
        assert r.state == WorkflowState.COMPLETED
        assert r.outputs == {}
        assert r.history == []
        assert r.error is None

    def test_to_dict(self) -> None:
        r = WorkflowResult(
            workflow_id="wf-1",
            state=WorkflowState.COMPLETED,
            outputs={"greeting": "hello"},
            history=[
                StepExecutionRecord(
                    step_id="s1",
                    step_name="S1",
                    step_type=StepType.AGENT,
                    started_at=0.0,
                    finished_at=0.1,
                    duration_ms=100.0,
                    success=True,
                    output={"text": "hello"},
                )
            ],
            duration_ms=200.0,
        )
        d = r.to_dict()
        assert d["workflow_id"] == "wf-1"
        assert d["state"] == "completed"
        assert d["outputs"] == {"greeting": "hello"}
        assert len(d["history"]) == 1
        assert d["history"][0]["step_id"] == "s1"

    def test_from_dict_roundtrip(self) -> None:
        original = WorkflowResult(
            workflow_id="wf-1",
            state=WorkflowState.FAILED,
            outputs={"x": 1},
            history=[
                StepExecutionRecord(
                    step_id="s1",
                    step_name="S1",
                    step_type=StepType.TOOL,
                    started_at=0.0,
                    finished_at=0.1,
                    duration_ms=100.0,
                    success=False,
                    attempts=3,
                    error="boom",
                )
            ],
            duration_ms=150.0,
            error="step failed",
        )
        d = original.to_dict()
        restored = WorkflowResult.from_dict(d)
        assert restored.workflow_id == "wf-1"
        assert restored.state == WorkflowState.FAILED
        assert restored.outputs == {"x": 1}
        assert len(restored.history) == 1
        assert restored.history[0].attempts == 3
        assert restored.history[0].error == "boom"
        assert restored.error == "step failed"

    def test_from_dict_invalid_state(self) -> None:
        with pytest.raises(ValueError, match="Unknown WorkflowState"):
            WorkflowResult.from_dict({"workflow_id": "wf-1", "state": "bogus"})

    def test_from_dict_invalid_type(self) -> None:
        with pytest.raises(ValueError):
            WorkflowResult.from_dict("not a dict")  # type: ignore[arg-type]
