"""
Tests for Planner, Plan, and PlanStep.
"""

from __future__ import annotations

import pytest

from core.plan import Plan, PlanStep, Planner


def test_plan_step_defaults() -> None:
    """PlanStep generates an ID and empty containers by default."""
    step = PlanStep()
    assert step.id
    assert step.description == ""
    assert step.tool_name == ""
    assert step.parameters == {}
    assert step.depends_on == []
    assert step.condition is None


def test_plan_step_is_conditional() -> None:
    """A step with a condition is conditional."""
    assert PlanStep(condition="x > 0").is_conditional()
    assert not PlanStep().is_conditional()


def test_plan_step_is_tool_step() -> None:
    """A step with a tool_name is a tool step."""
    assert PlanStep(tool_name="git_clone").is_tool_step()
    assert not PlanStep().is_tool_step()


def test_plan_defaults() -> None:
    """Plan generates an ID and empty step list by default."""
    plan = Plan()
    assert plan.id
    assert plan.objective == ""
    assert plan.steps == []


def test_plan_is_sequential_single_step() -> None:
    """A single-step plan is sequential."""
    plan = Plan(steps=[PlanStep()])
    assert plan.is_sequential()


def test_plan_is_sequential_multiple_steps() -> None:
    """A multi-step plan with chained dependencies is sequential."""
    s1 = PlanStep()
    s2 = PlanStep(depends_on=[s1.id])
    s3 = PlanStep(depends_on=[s2.id])
    plan = Plan(steps=[s1, s2, s3])
    assert plan.is_sequential()


def test_plan_is_not_sequential_when_forked() -> None:
    """A plan with a fork is not sequential."""
    s1 = PlanStep()
    s2 = PlanStep(depends_on=[s1.id])
    s3 = PlanStep(depends_on=[s1.id])  # fork
    plan = Plan(steps=[s1, s2, s3])
    assert not plan.is_sequential()


def test_plan_has_branches() -> None:
    """A plan with conditional steps has branches."""
    plan = Plan(steps=[
        PlanStep(condition="x > 0"),
        PlanStep(),
    ])
    assert plan.has_branches()


def test_plan_step_by_id() -> None:
    """Plan retrieves steps by ID."""
    step = PlanStep(description="find")
    plan = Plan(steps=[step])
    assert plan.step_by_id(step.id) is step
    assert plan.step_by_id("nonexistent") is None


def test_planner_plan_single_step() -> None:
    """Planner creates a single-step plan when no steps given."""
    planner = Planner()
    plan = planner.plan("research quantum computing")
    assert plan.objective == "research quantum computing"
    assert len(plan.steps) == 1
    assert "quantum" in plan.steps[0].description


def test_planner_plan_with_steps() -> None:
    """Planner wires dependencies for provided steps."""
    planner = Planner()
    steps = [
        PlanStep(description="search"),
        PlanStep(description="summarize"),
    ]
    plan = planner.plan("research", steps)
    assert len(plan.steps) == 2
    assert plan.steps[1].depends_on == [plan.steps[0].id]
    assert plan.is_sequential()


def test_planner_preserves_existing_dependencies() -> None:
    """Planner does not overwrite explicit dependencies."""
    planner = Planner()
    s1 = PlanStep(description="a")
    s2 = PlanStep(description="b", depends_on=[s1.id])
    s3 = PlanStep(description="c")  # no deps
    plan = planner.plan("test", [s1, s2, s3])
    assert plan.steps[1].depends_on == [s1.id]
    assert plan.steps[2].depends_on == [s2.id]  # auto-wired


def test_planner_plan_with_branches() -> None:
    """Planner creates conditional branch plans."""
    planner = Planner()
    plan = planner.plan_with_branches(
        "deploy",
        branches=[
            ("env == prod", [PlanStep(description="run tests")]),
            ("env == dev", [PlanStep(description="skip tests")]),
        ],
    )
    assert plan.objective == "deploy"
    assert len(plan.steps) == 2
    assert plan.has_branches()
    assert plan.steps[0].condition == "env == prod"
    assert plan.steps[1].condition == "env == dev"
