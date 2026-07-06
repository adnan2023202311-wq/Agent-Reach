"""
Planner layer for Milestone 3.

Provides:
- PlanStep: a single step in an execution plan
- Plan: an ordered collection of steps with an objective
- Planner: builds plans from objectives

This lives alongside the existing RuleBasedPlanner (core/planner.py)
which produces TaskPlan/SubTask for the kernel dispatcher. Plan and
PlanStep are runtime-layer constructs, not replacements.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PlanStep:
    """A single step in an execution plan.

    Attributes:
        id: Unique step identifier
        description: Human-readable step description
        tool_name: Optional tool to execute (empty for agent reasoning)
        parameters: Arguments for the tool or agent
        depends_on: Step IDs that must complete before this one
        condition: Optional conditional expression (simple string for now)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    tool_name: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    condition: Optional[str] = None

    def is_conditional(self) -> bool:
        return self.condition is not None

    def is_tool_step(self) -> bool:
        return bool(self.tool_name)


@dataclass
class Plan:
    """An ordered execution plan produced for an objective.

    Attributes:
        id: Unique plan identifier
        objective: The goal this plan addresses
        steps: Ordered list of plan steps
        created_at: ISO timestamp
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    objective: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: __import__("datetime").datetime.utcnow().isoformat())

    def is_sequential(self) -> bool:
        """True if every step depends only on the previous one."""
        if len(self.steps) <= 1:
            return True
        for i, step in enumerate(self.steps):
            if i == 0:
                if step.depends_on:
                    return False
            else:
                expected = [self.steps[i - 1].id]
                if step.depends_on != expected:
                    return False
        return True

    def has_branches(self) -> bool:
        """True if any step has a condition."""
        return any(step.is_conditional() for step in self.steps)

    def step_by_id(self, step_id: str) -> Optional[PlanStep]:
        """Retrieve a step by its ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None


class Planner:
    """Builds execution plans from objectives.

    Supports:
    - Sequential plans (default)
    - Conditional branches (via condition strings)

    Not yet supported:
    - Autonomous planning loops
    - LLM-driven plan generation
    """

    def __init__(self) -> None:
        self._strategies: dict[str, Any] = {}

    def plan(self, objective: str, steps: list[PlanStep] | None = None) -> Plan:
        """Build a plan from an objective and optional pre-defined steps.

        If no steps are provided, a simple sequential plan with one
        reasoning step is created.
        """
        if steps is None:
            steps = [PlanStep(description=f"Execute: {objective}")]
        else:
            # Auto-wire sequential dependencies if none provided
            steps = self._wire_dependencies(steps)

        return Plan(objective=objective, steps=steps)

    def plan_with_branches(
        self,
        objective: str,
        branches: list[tuple[str, list[PlanStep]]],
    ) -> Plan:
        """Build a plan with conditional branches.

        Args:
            objective: The overall goal
            branches: List of (condition, steps) tuples
        """
        all_steps: list[PlanStep] = []
        for condition, branch_steps in branches:
            for step in branch_steps:
                step.condition = condition
                all_steps.append(step)
        return self.plan(objective, all_steps)

    @staticmethod
    def _wire_dependencies(steps: list[PlanStep]) -> list[PlanStep]:
        """Auto-populate sequential dependencies for steps without any."""
        result: list[PlanStep] = []
        prev_id: Optional[str] = None
        for step in steps:
            new_step = PlanStep(
                id=step.id,
                description=step.description,
                tool_name=step.tool_name,
                parameters=step.parameters,
                depends_on=step.depends_on if step.depends_on else ([prev_id] if prev_id else []),
                condition=step.condition,
            )
            result.append(new_step)
            prev_id = new_step.id
        return result
