"""
Workflow & Orchestration Layer — WorkflowEngine (M5.2).

Layer: Application/Core — depends inward on domain/ and core/ only.

The WorkflowEngine executes :class:`~workflows.models.Workflow`
definitions built from the M5 model layer. It runs steps
sequentially (per the M5 spec — no DAG-style parallelism), supports
conditional branching via :class:`~workflows.models.Condition`,
merges outputs from multiple branches, retries failed steps per the
step's :class:`~domain.models.RetryPolicy`, and produces a
:class:`~workflows.models.WorkflowResult`.

This engine is deliberately distinct from the lower-level
capability-driven DAG engine in :py:mod:`workflow.engine` (M4),
which remains untouched. M4's engine orchestrates capabilities over
a DAG; M5's engine orchestrates NAMED workflows of agents and
tools, with persistence and validation as first-class concerns.

Synchronous execution contract:
The engine supports running a workflow with ``run_sync()`` — a
blocking, top-to-bottom execution — for the synchronous use case
the M5 spec explicitly calls out. It also exposes ``run()`` for
async use. Both share the same internal algorithm.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from domain.models import RetryPolicy, SubTask, TaskStatus
from workflows.conditions import evaluate_condition
from workflows.models import (
    StepExecutionRecord,
    StepType,
    Workflow,
    WorkflowContext,
    WorkflowResult,
    WorkflowState,
    WorkflowStep,
)
from workflows.orchestration import (
    AgentOrchestrator,
    OrchestrationResult,
    ToolOrchestrator,
    merge_outputs,
)
from workflows.template import resolve_optional, resolve_value

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Execute M5 Workflow definitions.

    Parameters
    ----------
    agent_orchestrator:
        Orchestrator for AGENT-type steps. If omitted, a default
        one is built without agents — only TOOL-type steps will
        work in that case.
    tool_orchestrator:
        Orchestrator for TOOL-type steps. If omitted, a default
        one is built with an empty ToolManager; tools must be
        registered before running a workflow that uses them.
    default_retry_policy:
        Applied to steps that don't override their own. If neither
        the step nor the engine provides one, attempts default to 1
        (no retry).
    """

    def __init__(
        self,
        agent_orchestrator: Optional[AgentOrchestrator] = None,
        tool_orchestrator: Optional[ToolOrchestrator] = None,
        default_retry_policy: Optional[RetryPolicy] = None,
    ) -> None:
        self._agent_orchestrator = agent_orchestrator
        self._tool_orchestrator = tool_orchestrator or ToolOrchestrator()
        self._default_retry_policy = default_retry_policy
        self._runs: dict[str, WorkflowResult] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def agent_orchestrator(self) -> Optional[AgentOrchestrator]:
        return self._agent_orchestrator

    @property
    def tool_orchestrator(self) -> ToolOrchestrator:
        return self._tool_orchestrator

    @property
    def default_retry_policy(self) -> Optional[RetryPolicy]:
        return self._default_retry_policy

    # ------------------------------------------------------------------
    # Run APIs
    # ------------------------------------------------------------------

    async def run(
        self,
        workflow: Workflow,
        initial_variables: Optional[dict[str, Any]] = None,
    ) -> WorkflowResult:
        """Execute ``workflow`` asynchronously.

        Steps run sequentially in declared order, skipping any step
        whose ``condition`` evaluates False. Failed steps are
        retried according to the step's (or engine's default)
        ``retry_policy``; if all attempts fail, the workflow is
        marked ``FAILED`` and execution stops.

        Returns a :class:`WorkflowResult` capturing every step's
        outcome plus the resolved workflow outputs.
        """
        return await self._run(workflow, initial_variables)

    def run_sync(
        self,
        workflow: Workflow,
        initial_variables: Optional[dict[str, Any]] = None,
    ) -> WorkflowResult:
        """Synchronous variant of :meth:`run`.

        Blocking, top-to-bottom execution. Useful for tests and
        workflows that don't need concurrent execution.
        """
        return asyncio.run(self._run(workflow, initial_variables))

    async def _run(
        self,
        workflow: Workflow,
        initial_variables: Optional[dict[str, Any]] = None,
    ) -> WorkflowResult:
        started_at = time.time()
        state = WorkflowState.RUNNING

        # Build the runtime context from workflow variables plus any
        # caller-provided overrides.
        variables: dict[str, Any] = dict(workflow.variables)
        if initial_variables:
            variables.update(initial_variables)

        context = WorkflowContext(
            workflow_id=workflow.workflow_id,
            variables=variables,
            metadata={"name": workflow.name, "version": workflow.version},
        )

        error: Optional[str] = None
        try:
            await self._execute_steps(workflow, context)
            state = WorkflowState.COMPLETED
        except _WorkflowFailed as exc:
            state = WorkflowState.FAILED
            error = str(exc)
        except Exception as exc:  # noqa: BLE001 - last-resort safety net
            state = WorkflowState.FAILED
            error = f"Workflow raised unexpected error: {exc}"
            logger.exception("Workflow %s failed unexpectedly", workflow.workflow_id)

        finished_at = time.time()
        outputs = self._resolve_workflow_outputs(workflow, context)

        result = WorkflowResult(
            workflow_id=workflow.workflow_id,
            state=state,
            outputs=outputs,
            history=list(context.history),
            duration_ms=(finished_at - started_at) * 1000.0,
            error=error,
            started_at=started_at,
            finished_at=finished_at,
        )
        self._runs[workflow.workflow_id] = result
        return result

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    async def _execute_steps(
        self,
        workflow: Workflow,
        context: WorkflowContext,
    ) -> None:
        """Run all steps in declared order.

        Each step's ``condition`` is evaluated against the current
        context; a step whose condition is False is recorded as
        skipped and not executed. After all immediate dependencies
        complete (best-effort), the step itself runs and any output
        keys it declares are placed into ``context.step_outputs``.
        """
        for step in workflow.steps:
            await self._execute_step(workflow, step, context)

    async def _execute_step(
        self,
        workflow: Workflow,
        step: WorkflowStep,
        context: WorkflowContext,
    ) -> None:
        """Run a single step, recording the outcome in context.history.

        Honors ``depends_on`` by skipping the step if any dependency
        did not produce a successful output. Honors ``condition``
        by skipping the step when the condition is False. Retries
        failed attempts per the resolved retry policy.
        """
        started_at = time.time()

        # Dependency check — if a required dep failed or was skipped,
        # skip this step too rather than crash with confusing errors.
        for dep_id in step.depends_on:
            dep_record = self._find_record(context, dep_id)
            if dep_record is None:
                # No record means the dependency was never executed
                # (out-of-order declaration). Treat as a structural
                # error and fail the workflow.
                raise _WorkflowFailed(
                    f"Step '{step.step_id}' depends on '{dep_id}', "
                    f"but '{dep_id}' was never executed (declared after "
                    f"'{step.step_id}' or in a skipped branch)."
                )
            # Treat both failure and skip as "did not produce output";
            # a dependent step should not run on an absent input.
            if not dep_record.success or dep_record.skipped:
                finished_at = time.time()
                context.history.append(
                    StepExecutionRecord(
                        step_id=step.step_id,
                        step_name=step.name,
                        step_type=step.type,
                        started_at=started_at,
                        finished_at=finished_at,
                        duration_ms=(finished_at - started_at) * 1000.0,
                        success=True,
                        skipped=True,
                        error=f"dependency '{dep_id}' did not succeed",
                    )
                )
                return

        # Conditional evaluation — skip silently when condition is False.
        if step.condition is not None and not evaluate_condition(step.condition, context):
            finished_at = time.time()
            context.history.append(
                StepExecutionRecord(
                    step_id=step.step_id,
                    step_name=step.name,
                    step_type=step.type,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=(finished_at - started_at) * 1000.0,
                    success=True,
                    skipped=True,
                )
            )
            return

        # Resolve inputs against the current context.
        try:
            resolved_inputs = resolve_value(step.inputs, context)
        except KeyError as exc:
            finished_at = time.time()
            context.history.append(
                StepExecutionRecord(
                    step_id=step.step_id,
                    step_name=step.name,
                    step_type=step.type,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=(finished_at - started_at) * 1000.0,
                    success=False,
                    error=f"Input template references missing variable: {exc}",
                )
            )
            raise _WorkflowFailed(
                f"Step '{step.step_id}' input template references missing variable: {exc}"
            )

        # Execute with retries.
        #
        # Per docs/MILESTONE_5_SPECIFICATION.md (v1.1, Semantic
        # Definitions — StepExecutionRecord.attempts):
        #
        #     attempts records the number of times the
        #     WorkflowEngine invoked the step, bounded by the
        #     resolved RetryPolicy.max_attempts. Inner
        #     orchestrator retries are an implementation detail
        #     of that orchestrator and are NOT reflected in
        #     this field.
        #
        # So we count engine-level invocations only. The
        # underlying OrchestrationResult.attempts is preserved
        # for callers that want the inner-retry count via the
        # engine\'s internal accessors, but the audit record
        # only reports the outer (workflow-level) count.
        policy = self._resolve_retry_policy(workflow, step)
        last: OrchestrationResult
        engine_attempts = 0
        for attempt in range(1, policy.max_attempts + 1):
            engine_attempts = attempt
            try:
                outcome = await self._invoke(step, resolved_inputs)
            except Exception as exc:  # noqa: BLE001 - orchestrator must never raise
                outcome = OrchestrationResult(
                    success=False,
                    error=f"orchestrator raised: {exc}",
                    attempts=1,
                )

            if outcome.success:
                last = outcome
                break

            last = outcome
            if attempt < policy.max_attempts:
                if policy.backoff_seconds > 0:
                    await asyncio.sleep(policy.backoff_seconds * attempt)
        else:
            # Loop completed without a successful break — all attempts failed.
            last = last  # type: ignore[assignment]

        finished_at = time.time()
        record = StepExecutionRecord(
            step_id=step.step_id,
            step_name=step.name,
            step_type=step.type,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=(finished_at - started_at) * 1000.0,
            success=last.success,
            # Per the M5 spec amendment: this is the number of
            # times the WorkflowEngine invoked the step, NOT the
            # total underlying invocations.
            attempts=engine_attempts,
            output=last.output if last.success else None,
            error=last.error,
        )
        context.history.append(record)

        # Propagate declared outputs into the context for downstream steps.
        if last.success and step.output_keys:
            outputs = self._extract_outputs(step, last.output)
            context.step_outputs[step.step_id] = outputs

        if not last.success:
            raise _WorkflowFailed(
                f"Step '{step.step_id}' ({step.name}) failed after "
                f"{engine_attempts} attempt(s): {last.error}"
            )

    async def _invoke(
        self,
        step: WorkflowStep,
        resolved_inputs: dict[str, Any],
    ) -> OrchestrationResult:
        """Dispatch a step to the appropriate orchestrator."""
        if step.type is StepType.AGENT:
            if self._agent_orchestrator is None:
                return OrchestrationResult(
                    success=False,
                    error="No agent orchestrator configured",
                )
            description = step.name or step.step_id
            return await self._agent_orchestrator.execute(
                agent_type_str=step.target,
                inputs=resolved_inputs,
                description=description,
            )

        if step.type is StepType.TOOL:
            return await self._tool_orchestrator.execute(
                tool_name=step.target,
                inputs=resolved_inputs,
                agent_type_str="",
                timeout_seconds=step.timeout_seconds,
            )

        return OrchestrationResult(
            success=False,
            error=f"Unknown StepType: {step.type!r}",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_retry_policy(
        self, workflow: Workflow, step: WorkflowStep
    ) -> RetryPolicy:
        """Pick a RetryPolicy for ``step``: step-level → workflow → engine default → 1/0."""
        if step.retry_policy is not None:
            return step.retry_policy
        if workflow.default_retry_policy is not None:
            return workflow.default_retry_policy
        if self._default_retry_policy is not None:
            return self._default_retry_policy
        return RetryPolicy(max_attempts=1, backoff_seconds=0.0, timeout_seconds=30.0)

    @staticmethod
    def _find_record(context: WorkflowContext, step_id: str) -> Optional[StepExecutionRecord]:
        for r in context.history:
            if r.step_id == step_id:
                return r
        return None

    @staticmethod
    def _extract_outputs(
        step: WorkflowStep, output: Any
    ) -> dict[str, Any]:
        """Pick the declared output keys from a step's raw output.

        - If ``output`` is a dict, only declared keys are kept.
        - If ``output`` is not a dict, the entire value is stored
          under each declared key (so a scalar tool result can be
          exposed under any output name the workflow needs).
        """
        if isinstance(output, dict):
            return {k: output[k] for k in step.output_keys if k in output}
        return {k: output for k in step.output_keys}

    @staticmethod
    def _resolve_workflow_outputs(
        workflow: Workflow, context: WorkflowContext
    ) -> dict[str, Any]:
        """Resolve the Workflow's named outputs from the final context.

        Each entry in ``workflow.outputs`` is a name → path map
        (``"variables.x"`` or ``"outputs.step_id.key"``). Missing
        paths become ``None`` rather than raising, so a partial
        workflow run still produces a well-formed result.
        """
        resolved: dict[str, Any] = {}
        for name, path in workflow.outputs.items():
            resolved[name] = resolve_optional(path, context)
        return resolved

    # ------------------------------------------------------------------
    # Result accessors
    # ------------------------------------------------------------------

    def get_result(self, workflow_id: str) -> Optional[WorkflowResult]:
        return self._runs.get(workflow_id)

    def list_results(self) -> list[WorkflowResult]:
        return list(self._runs.values())

    def clear(self) -> None:
        """Drop all stored results. Useful for testing."""
        self._runs.clear()


class _WorkflowFailed(Exception):
    """Internal control-flow exception: abort the current workflow run."""

    pass
