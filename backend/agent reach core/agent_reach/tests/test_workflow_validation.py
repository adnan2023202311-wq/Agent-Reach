"""Unit tests for Workflow Validation (M5.7)."""

from __future__ import annotations

import pytest

from core.dispatcher import AgentDispatcher
from core.tool_executor import ToolExecutor
from domain.models import AgentType, RetryPolicy
from workflows.models import (
    Condition,
    ConditionOp,
    StepType,
    Workflow,
    WorkflowStep,
)
from workflows.validation import (
    ValidationResult,
    WorkflowValidator,
    validate_many,
    validate_structure,
)


class _FakeAgent:
    """Echo agent that returns a fixed dict — used for validator tests."""

    def __init__(self, agent_type: AgentType) -> None:
        self._type = agent_type

    @property
    def agent_type(self) -> AgentType:
        return self._type

    async def execute(self, subtask):  # noqa: ANN001 - test helper
        return {"text": f"echo:{subtask.description}"}


def _make_dispatcher() -> AgentDispatcher:
    return AgentDispatcher(
        agents={
            AgentType.RESEARCH: _FakeAgent(AgentType.RESEARCH),
            AgentType.CODING: _FakeAgent(AgentType.CODING),
        },
        retry_policy=RetryPolicy(max_attempts=1),
    )


def _make_executor() -> ToolExecutor:
    ex = ToolExecutor()

    async def add(a: int = 0, b: int = 0) -> int:
        return a + b

    ex.register_tool("add", add)
    return ex


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------


class TestValidateStructureBasic:
    def test_valid_workflow(self) -> None:
        wf = Workflow(
            name="ok",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 1},
                    output_keys=["sum"],
                )
            ],
            outputs={"total": "outputs.s1.sum"},
        )
        result = validate_structure(wf)
        assert result.valid is True
        assert result.errors == []

    def test_empty_name_is_error(self) -> None:
        wf = Workflow(
            name="",
            steps=[
                WorkflowStep(step_id="s1", type=StepType.TOOL, target="add"),
            ],
        )
        result = validate_structure(wf)
        assert result.valid is False
        assert any("name must be non-empty" in e for e in result.errors)

    def test_missing_target_is_error(self) -> None:
        wf = Workflow(
            name="x",
            steps=[WorkflowStep(step_id="s1", type=StepType.TOOL, target="")],
        )
        result = validate_structure(wf)
        assert result.valid is False
        assert any("no target" in e for e in result.errors)

    def test_duplicate_step_id_is_error(self) -> None:
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(step_id="dup", type=StepType.TOOL, target="add"),
                WorkflowStep(step_id="dup", type=StepType.TOOL, target="add"),
            ],
        )
        result = validate_structure(wf)
        assert result.valid is False
        assert any("Duplicate step_id" in e for e in result.errors)

    def test_self_dependency_is_error(self) -> None:
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    depends_on=["s1"],
                )
            ],
        )
        result = validate_structure(wf)
        assert result.valid is False
        assert any("depends on itself" in e for e in result.errors)

    def test_unknown_dependency_is_error(self) -> None:
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    depends_on=["ghost"],
                )
            ],
        )
        result = validate_structure(wf)
        assert result.valid is False
        assert any("depends on unknown step" in e for e in result.errors)

    def test_no_steps_is_warning(self) -> None:
        wf = Workflow(name="empty")
        result = validate_structure(wf)
        # No errors, but a warning is added.
        assert result.valid is True
        assert any("no steps" in w for w in result.warnings)


class TestValidateStructureCycles:
    def test_two_step_cycle(self) -> None:
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="a",
                    type=StepType.TOOL,
                    target="add",
                    depends_on=["b"],
                ),
                WorkflowStep(
                    step_id="b",
                    type=StepType.TOOL,
                    target="add",
                    depends_on=["a"],
                ),
            ],
        )
        result = validate_structure(wf)
        assert result.valid is False
        assert any("cycle" in e for e in result.errors)

    def test_three_step_cycle(self) -> None:
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(step_id="a", type=StepType.TOOL, target="add", depends_on=["c"]),
                WorkflowStep(step_id="b", type=StepType.TOOL, target="add", depends_on=["a"]),
                WorkflowStep(step_id="c", type=StepType.TOOL, target="add", depends_on=["b"]),
            ],
        )
        result = validate_structure(wf)
        assert result.valid is False
        assert any("cycle" in e for e in result.errors)

    def test_no_cycle_dag(self) -> None:
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(step_id="a", type=StepType.TOOL, target="add"),
                WorkflowStep(step_id="b", type=StepType.TOOL, target="add", depends_on=["a"]),
                WorkflowStep(step_id="c", type=StepType.TOOL, target="add", depends_on=["a", "b"]),
            ],
        )
        result = validate_structure(wf)
        assert result.valid is True


class TestValidateStructureTemplateRefs:
    def test_valid_variable_reference(self) -> None:
        wf = Workflow(
            name="x",
            variables={"x": 5},
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": "{{ variables.x }}", "b": 1},
                )
            ],
        )
        result = validate_structure(wf)
        assert result.valid is True

    def test_undefined_variable_in_input_is_error(self) -> None:
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": "{{ variables.ghost }}", "b": 1},
                )
            ],
        )
        result = validate_structure(wf)
        assert result.valid is False
        assert any("undefined variable" in e for e in result.errors)

    def test_undefined_bare_path_is_error(self) -> None:
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": "variables.ghost", "b": 1},
                )
            ],
        )
        result = validate_structure(wf)
        assert result.valid is False
        assert any("undefined variable" in e for e in result.errors)

    def test_valid_step_output_reference(self) -> None:
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 1},
                    output_keys=["sum"],
                ),
                WorkflowStep(
                    step_id="s2",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": "{{ outputs.s1.sum }}", "b": 1},
                ),
            ],
        )
        result = validate_structure(wf)
        assert result.valid is True

    def test_forward_step_output_reference_is_error(self) -> None:
        # s2 references outputs.s1.sum, but s1 is declared AFTER s2.
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s2",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": "{{ outputs.s1.sum }}", "b": 1},
                ),
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 1},
                    output_keys=["sum"],
                ),
            ],
        )
        result = validate_structure(wf)
        assert result.valid is False
        assert any("not run yet" in e for e in result.errors)

    def test_workflow_output_to_undefined_step_is_error(self) -> None:
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 1},
                    output_keys=["sum"],
                )
            ],
            outputs={"x": "outputs.ghost.sum"},
        )
        result = validate_structure(wf)
        assert result.valid is False
        assert any("unknown step" in e for e in result.errors)

    def test_workflow_output_to_undefined_variable_is_error(self) -> None:
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 1},
                )
            ],
            outputs={"x": "variables.ghost"},
        )
        result = validate_structure(wf)
        assert result.valid is False
        assert any("undefined variable" in e for e in result.errors)

    def test_malformed_workflow_output_is_error(self) -> None:
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 1},
                )
            ],
            outputs={"x": "outputs.s1"},
        )
        result = validate_structure(wf)
        assert result.valid is False
        assert any("malformed outputs path" in e for e in result.errors)


class TestValidateStructureConditions:
    def test_valid_condition_on_variable(self) -> None:
        wf = Workflow(
            name="x",
            variables={"go": True},
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    condition=Condition("go", ConditionOp.TRUTHY),
                )
            ],
        )
        result = validate_structure(wf)
        assert result.valid is True

    def test_valid_condition_on_step_output(self) -> None:
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 1},
                    output_keys=["sum"],
                ),
                WorkflowStep(
                    step_id="s2",
                    type=StepType.TOOL,
                    target="add",
                    condition=Condition(
                        "outputs.s1.sum", ConditionOp.GTE, value=2
                    ),
                ),
            ],
        )
        result = validate_structure(wf)
        assert result.valid is True

    def test_undefined_condition_variable_is_error(self) -> None:
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    condition=Condition("variables.ghost", ConditionOp.TRUTHY),
                )
            ],
        )
        result = validate_structure(wf)
        assert result.valid is False
        assert any("condition references" in e for e in result.errors)


# ---------------------------------------------------------------------------
# WorkflowValidator (registry-aware)
# ---------------------------------------------------------------------------


class TestWorkflowValidator:
    def test_missing_agent_is_error(self) -> None:
        dispatcher = _make_dispatcher()
        validator = WorkflowValidator(dispatcher=dispatcher)
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.AGENT,
                    target="writing",  # not registered
                )
            ],
        )
        result = validator.validate(wf)
        assert result.valid is False
        assert any("unregistered agent" in e for e in result.errors)

    def test_registered_agent_is_ok(self) -> None:
        dispatcher = _make_dispatcher()
        validator = WorkflowValidator(dispatcher=dispatcher)
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.AGENT,
                    target="research",
                )
            ],
        )
        result = validator.validate(wf)
        assert result.valid is True

    def test_missing_tool_is_error(self) -> None:
        executor = _make_executor()
        validator = WorkflowValidator(executor=executor)
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="divide",  # not registered
                )
            ],
        )
        result = validator.validate(wf)
        assert result.valid is False
        assert any("unregistered tool" in e for e in result.errors)

    def test_registered_tool_is_ok(self) -> None:
        executor = _make_executor()
        validator = WorkflowValidator(executor=executor)
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                )
            ],
        )
        result = validator.validate(wf)
        assert result.valid is True

    def test_no_dispatcher_skips_agent_check(self) -> None:
        validator = WorkflowValidator(dispatcher=None)
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.AGENT,
                    target="any-agent",
                )
            ],
        )
        result = validator.validate(wf)
        # No agent check performed, but structure is OK.
        assert result.valid is True

    def test_structural_errors_still_caught(self) -> None:
        dispatcher = _make_dispatcher()
        validator = WorkflowValidator(dispatcher=dispatcher)
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="a",
                    type=StepType.AGENT,
                    target="research",
                    depends_on=["b"],
                ),
                WorkflowStep(
                    step_id="b",
                    type=StepType.AGENT,
                    target="research",
                    depends_on=["a"],
                ),
            ],
        )
        result = validator.validate(wf)
        assert result.valid is False
        assert any("cycle" in e for e in result.errors)


class TestValidateMany:
    def test_returns_map_by_name(self) -> None:
        good = Workflow(
            name="good",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                )
            ],
        )
        # Name and structure are both valid here. The test
        # exercises validate_many's API (returns a map keyed by
        # name) rather than the empty-name error path which is
        # covered by test_empty_name_is_error above.
        # A workflow with a real structural error so we can
        # assert the "bad" key maps to an invalid result.
        bad = Workflow(
            name="bad",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    depends_on=["ghost"],
                )
            ],
        )
        results = validate_many([good, bad])
        assert "good" in results and "bad" in results
        assert results["good"].valid is True
        assert results["bad"].valid is False

    def test_uses_validator_when_provided(self) -> None:
        dispatcher = _make_dispatcher()
        validator = WorkflowValidator(dispatcher=dispatcher)
        wf = Workflow(
            name="missing_agent",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.AGENT,
                    target="ghost_agent",
                )
            ],
        )
        results = validate_many([wf], validator=validator)
        assert results["missing_agent"].valid is False
        assert any("unregistered agent" in e for e in results["missing_agent"].errors)


class TestValidationResult:
    def test_add_error_sets_invalid(self) -> None:
        r = ValidationResult()
        assert r.valid is True
        r.add_error("boom")
        assert r.valid is False
        assert r.errors == ["boom"]

    def test_add_warning_keeps_valid(self) -> None:
        r = ValidationResult()
        r.add_warning("careful")
        assert r.valid is True
        assert r.warnings == ["careful"]

    def test_merge(self) -> None:
        a = ValidationResult()
        a.add_error("a-error")
        b = ValidationResult()
        b.add_warning("b-warning")
        a.merge(b)
        assert a.errors == ["a-error"]
        assert a.warnings == ["b-warning"]
        assert a.valid is False

    def test_merge_invalidates_when_other_invalid(self) -> None:
        a = ValidationResult()
        b = ValidationResult()
        b.add_error("b-error")
        a.merge(b)
        assert a.valid is False
