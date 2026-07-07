"""
Workflow Engine for Milestone 4.

Per ADR-004: Planner never executes. Execution Engine never plans.
Workflow Engine owns orchestration.

Inspired by LangGraph's DAG workflow, checkpoints, and state management,
but built natively without framework lock-in.

Provides:
- WorkflowStep: a node in the workflow DAG
- WorkflowState: lifecycle states for a workflow run
- WorkflowCheckpoint: serializable snapshot of workflow state
- WorkflowEngine: orchestrates step execution with dependency resolution,
  checkpointing, evaluation, and reflection integration

Layer: Application/Core — depends inward on domain/ and infrastructure/ only.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from core.capability_resolver import CapabilityResolver
from core.execution import ExecutionOrchestrator, ExecutionOutcome, ExecutionStep
from evaluation.engine import EvaluationEngine, EvaluationReport
from observability.tracing import ObservabilityCollector
from reflection.engine import ReflectionEngine, ReflectionReport


class WorkflowState(str, Enum):
    """Finite state machine for workflow execution."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowStep:
    """A single step in a workflow DAG.

    Attributes:
        step_id: Unique identifier
        name: Human-readable name
        capability_id: Capability to resolve and execute
        inputs: Input parameters
        depends_on: Step IDs that must complete before this one
        evaluate: Whether to run evaluation after this step
        reflect: Whether to run reflection after this step
    """

    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    capability_id: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    evaluate: bool = False
    reflect: bool = False


@dataclass
class StepOutcome:
    """Outcome of executing one workflow step."""

    step_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    evaluation: Optional[EvaluationReport] = None
    reflection: Optional[ReflectionReport] = None


@dataclass
class WorkflowCheckpoint:
    """Serializable snapshot of workflow execution state."""

    workflow_id: str
    state: WorkflowState
    completed_steps: list[str] = field(default_factory=list)
    step_outcomes: dict[str, StepOutcome] = field(default_factory=dict)
    created_at: float = field(default_factory=time.perf_counter)


@dataclass
class WorkflowResult:
    """Final result of a workflow execution."""

    workflow_id: str
    state: WorkflowState
    step_outcomes: dict[str, StepOutcome] = field(default_factory=dict)
    duration_ms: float = 0.0
    error: Optional[str] = None


class WorkflowEngine:
    """Orchestrates DAG workflow execution with checkpoints.

    The Workflow Engine is the central coordinator of Milestone 4.
    It owns the execution order and integrates all M4 subsystems.
    """

    def __init__(
        self,
        capability_resolver: CapabilityResolver,
        execution_orchestrator: Optional[ExecutionOrchestrator] = None,
        evaluation_engine: Optional[EvaluationEngine] = None,
        reflection_engine: Optional[ReflectionEngine] = None,
        observability: Optional[ObservabilityCollector] = None,
    ) -> None:
        self._capability_resolver = capability_resolver
        self._execution = execution_orchestrator or ExecutionOrchestrator(
            capability_resolver, observability
        )
        self._evaluation = evaluation_engine
        self._reflection = reflection_engine
        self._observability = observability or ObservabilityCollector()
        self._workflows: dict[str, WorkflowResult] = {}

    @property
    def capability_resolver(self) -> CapabilityResolver:
        return self._capability_resolver

    def create_checkpoint(self, workflow_id: str, state: WorkflowState, outcomes: dict[str, StepOutcome]) -> WorkflowCheckpoint:
        """Create a checkpoint from current execution state."""
        return WorkflowCheckpoint(
            workflow_id=workflow_id,
            state=state,
            completed_steps=list(outcomes.keys()),
            step_outcomes=dict(outcomes),
        )

    async def run(
        self,
        workflow_id: str,
        steps: list[WorkflowStep],
        resume_from: Optional[WorkflowCheckpoint] = None,
    ) -> WorkflowResult:
        """Execute a workflow.

        Args:
            workflow_id: Unique workflow identifier
            steps: DAG of workflow steps
            resume_from: Optional checkpoint to resume from

        Returns:
            WorkflowResult with all outcomes
        """
        start = time.perf_counter()
        outcomes: dict[str, StepOutcome] = {}

        if resume_from is not None:
            outcomes = dict(resume_from.step_outcomes)

        state = WorkflowState.RUNNING
        remaining = {
            s.step_id: s for s in steps
            if s.step_id not in outcomes
        }

        error: Optional[str] = None
        try:
            while remaining:
                # Find ready steps
                ready = [
                    s for s in remaining.values()
                    if all(d in outcomes for d in s.depends_on)
                ]

                if not ready:
                    state = WorkflowState.FAILED
                    error = "Circular or unsatisfiable dependency detected"
                    break

                # Execute ready steps concurrently
                tasks = [self._run_step(s) for s in ready]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for step, result in zip(ready, batch_results):
                    if isinstance(result, Exception):
                        outcomes[step.step_id] = StepOutcome(
                            step_id=step.step_id,
                            success=False,
                            error=f"Unexpected error: {result}",
                        )
                        state = WorkflowState.FAILED
                    else:
                        outcomes[step.step_id] = result
                        if not result.success:
                            state = WorkflowState.FAILED

                    del remaining[step.step_id]

                if state == WorkflowState.FAILED:
                    break

            if state != WorkflowState.FAILED:
                state = WorkflowState.COMPLETED

        except Exception as exc:
            state = WorkflowState.FAILED
            error = str(exc)

        result = WorkflowResult(
            workflow_id=workflow_id,
            state=state,
            step_outcomes=outcomes,
            duration_ms=(time.perf_counter() - start) * 1000,
            error=error,
        )
        self._workflows[workflow_id] = result
        return result

    async def _run_step(self, step: WorkflowStep) -> StepOutcome:
        """Execute a single workflow step with optional evaluation and reflection."""
        exec_step = ExecutionStep(
            step_id=step.step_id,
            capability_id=step.capability_id,
            inputs=step.inputs,
        )
        exec_outcome = await self._execution.execute_step(exec_step)

        evaluation: Optional[EvaluationReport] = None
        reflection: Optional[ReflectionReport] = None

        if step.evaluate and self._evaluation is not None and exec_outcome.success:
            evaluation = self._evaluation.evaluate(output=exec_outcome.output)

        if step.reflect and self._reflection is not None and evaluation is not None:
            reflection = self._reflection.reflect(evaluation)

        return StepOutcome(
            step_id=step.step_id,
            success=exec_outcome.success,
            output=exec_outcome.output,
            error=exec_outcome.error,
            duration_ms=exec_outcome.duration_ms,
            evaluation=evaluation,
            reflection=reflection,
        )

    def get_result(self, workflow_id: str) -> Optional[WorkflowResult]:
        """Retrieve the result of a workflow execution."""
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> list[WorkflowResult]:
        """List all workflow results."""
        return list(self._workflows.values())

    def clear(self) -> None:
        """Remove all workflow results. Useful for testing."""
        self._workflows.clear()
        self._observability.clear()
