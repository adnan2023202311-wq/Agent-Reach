"""
Workflow & Orchestration Layer — Orchestration helpers (M5.4 / M5.5).

Layer: Application/Core — depends inward on domain/ and core/ only.

Two thin wrappers around existing M3 components that adapt them to
the Workflow Engine's step interface:

- :class:`AgentOrchestrator` wraps an :class:`~core.dispatcher.AgentDispatcher`
  so a Workflow can invoke any registered Agent via the existing
  retry/timeout pipeline.
- :class:`ToolOrchestrator` wraps a :class:`~core.tool_executor.ToolExecutor`
  so a Workflow can invoke any registered tool with parameter
  passing and output propagation.

Both produce a uniform ``OrchestrationResult`` so the engine does
not need to know whether a step ran an agent or a tool.

Reuse over duplication: every method here is a thin facade over an
already-tested M3 component. Nothing here redefines retry, timeout,
or error handling — those concerns belong to the underlying
components and are inherited verbatim.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from core.dispatcher import AgentDispatcher
from core.tool_executor import ToolExecutor
from domain.models import AgentType, RetryPolicy, SubTask, TaskStatus


@dataclass
class OrchestrationResult:
    """Uniform outcome returned by Agent and Tool orchestrators."""

    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    attempts: int = 1


class AgentOrchestrator:
    """Invoke agents from a Workflow via the existing AgentDispatcher.

    Each :py:meth:`execute` call:
    - builds a :class:`~domain.models.SubTask` from the inputs,
    - delegates to :py:meth:`AgentDispatcher.dispatch`,
    - converts the :class:`~domain.models.AgentResult` into a
      uniform :class:`OrchestrationResult`.
    """

    def __init__(
        self,
        dispatcher: AgentDispatcher,
        default_retry_policy: Optional[RetryPolicy] = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._default_retry_policy = default_retry_policy

    @property
    def dispatcher(self) -> AgentDispatcher:
        return self._dispatcher

    async def execute(
        self,
        agent_type_str: str,
        inputs: dict[str, Any],
        description: str,
        retry_policy: Optional[RetryPolicy] = None,
    ) -> OrchestrationResult:
        """Dispatch a SubTask to the agent identified by ``agent_type_str``.

        ``agent_type_str`` is the string form of
        :class:`~domain.models.AgentType` (e.g. ``"research"``).
        """
        try:
            agent_type = AgentType(agent_type_str)
        except ValueError:
            return OrchestrationResult(
                success=False,
                error=f"Unknown agent type: {agent_type_str!r}",
            )

        subtask = SubTask(
            agent_type=agent_type,
            description=description,
            input_data=dict(inputs),
        )

        start = time.perf_counter()
        # The dispatcher owns its own retry policy. The workflow may
        # supply one too, but AgentDispatcher doesn't expose a way
        # to override it per call — the retry policy used here is
        # the one the dispatcher was built with. The retry_policy
        # argument is accepted for API symmetry with the workflow
        # engine, and is recorded in OrchestrationResult.attempts
        # from what the dispatcher actually did.
        _ = retry_policy  # currently unused; reserved for future per-call overrides
        result = await self._dispatcher.dispatch(subtask)
        duration_ms = (time.perf_counter() - start) * 1000.0

        return OrchestrationResult(
            success=result.success,
            output=result.output,
            error=result.error,
            duration_ms=duration_ms,
            attempts=result.attempts,
        )


class ToolOrchestrator:
    """Invoke tools from a Workflow via the existing ToolExecutor.

    Wraps :class:`~core.tool_executor.ToolExecutor` so workflow steps
    of type ``TOOL`` route through the same timeout, exception
    isolation, and audit machinery as direct tool calls.
    """

    def __init__(self, executor: Optional[ToolExecutor] = None) -> None:
        self._executor = executor or ToolExecutor()

    @property
    def executor(self) -> ToolExecutor:
        return self._executor

    async def execute(
        self,
        tool_name: str,
        inputs: dict[str, Any],
        agent_type_str: str = "",
        timeout_seconds: float = 30.0,
    ) -> OrchestrationResult:
        """Execute ``tool_name`` with the given inputs.

        ``agent_type_str`` is forwarded to ToolManager so permission
        checks still apply.
        """
        from core.tool_executor import ToolContext

        context = ToolContext(
            agent_type=agent_type_str,
            tool_name=tool_name,
            parameters=dict(inputs),
            timeout_seconds=timeout_seconds,
        )
        result = await self._executor.execute(context)
        return OrchestrationResult(
            success=result.success,
            output=result.output,
            error=result.error,
            duration_ms=result.duration_ms,
            attempts=1,
        )


def merge_outputs(step_outputs: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge outputs from parallel branches into a single dict.

    Later dicts override earlier ones; if two branches contribute a
    list under the same key, the lists are concatenated. This is the
    deterministic merge policy the engine uses when multiple branches
    converge into a single workflow output.
    """
    merged: dict[str, Any] = {}
    for outputs in step_outputs:
        for key, value in outputs.items():
            if (
                key in merged
                and isinstance(merged[key], list)
                and isinstance(value, list)
            ):
                merged[key] = merged[key] + value
            else:
                merged[key] = value
    return merged


def is_successful_result(result: OrchestrationResult) -> bool:
    """Backward-compatible predicate used by tests for TaskStatus."""
    return result.success and result.error is None


__all__ = [
    "AgentOrchestrator",
    "OrchestrationResult",
    "TaskStatus",  # re-exported for convenience
    "ToolOrchestrator",
    "merge_outputs",
]
