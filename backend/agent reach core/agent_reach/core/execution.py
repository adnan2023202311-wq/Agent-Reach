"""
Execution Engine Improvements for Milestone 4.

Enhances the kernel's execution capabilities by integrating:
- CapabilityResolver for tool/agent routing (ADR-005)
- ObservabilityCollector for execution tracing (ADR-006)
- Parallel execution of independent steps
- Exception isolation and metrics collection

This does NOT replace the plugin system's ExecutionEngine or M3's
ToolExecutor — it orchestrates them at the kernel level.

Layer: Application/Core — depends inward on domain/ and infrastructure/ only.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from core.capability_resolver import CapabilityResolver
from observability.tracing import ObservabilityCollector, SpanStatus


@dataclass
class ExecutionStep:
    """A single step in an execution batch."""

    step_id: str
    capability_id: str
    inputs: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class ExecutionOutcome:
    """Outcome of executing one step."""

    step_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0


class ExecutionOrchestrator:
    """Orchestrates execution with capability resolution and tracing.

    Integrates the CapabilityResolver so that no caller needs to
    hold direct references to executors. Every execution is traced
    via the ObservabilityCollector.
    """

    def __init__(
        self,
        capability_resolver: CapabilityResolver,
        observability: Optional[ObservabilityCollector] = None,
    ) -> None:
        self._resolver = capability_resolver
        self._observability = observability or ObservabilityCollector()

    @property
    def observability(self) -> ObservabilityCollector:
        return self._observability

    async def execute_step(self, step: ExecutionStep) -> ExecutionOutcome:
        """Execute a single step with resolution, tracing, and isolation.

        Args:
            step: The execution step

        Returns:
            ExecutionOutcome with output or error
        """
        trace = self._observability.start_trace()
        span = self._observability.start_span(
            trace.trace_id,
            f"execute_step:{step.capability_id}",
            attributes={"step_id": step.step_id, "capability_id": step.capability_id},
        )

        start = time.perf_counter()
        resolved = self._resolver.resolve(step.capability_id)

        if resolved is None:
            error = f"Capability '{step.capability_id}' could not be resolved"
            self._observability.end_span(trace.trace_id, span.span_id, SpanStatus.ERROR)
            self._observability.end_trace(trace.trace_id)
            return ExecutionOutcome(
                step_id=step.step_id,
                success=False,
                error=error,
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        try:
            output = await resolved.executor(**step.inputs)
            duration_ms = (time.perf_counter() - start) * 1000
            self._observability.end_span(trace.trace_id, span.span_id, SpanStatus.OK)
            self._observability.end_trace(trace.trace_id)
            return ExecutionOutcome(
                step_id=step.step_id,
                success=True,
                output=output,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._observability.end_span(trace.trace_id, span.span_id, SpanStatus.ERROR)
            self._observability.end_trace(trace.trace_id)
            return ExecutionOutcome(
                step_id=step.step_id,
                success=False,
                error=f"Execution failed: {exc}",
                duration_ms=duration_ms,
            )

    async def execute_batch(self, steps: list[ExecutionStep]) -> list[ExecutionOutcome]:
        """Execute a batch of steps, respecting dependencies.

        Steps with no dependencies run concurrently. Steps with
        dependencies wait for their prerequisites to complete.

        Args:
            steps: List of execution steps

        Returns:
            List of ExecutionOutcomes in the same order as input
        """
        outcomes: dict[str, ExecutionOutcome] = {}
        remaining = {s.step_id: s for s in steps}

        while remaining:
            # Find steps whose dependencies are all satisfied
            ready = [
                s for s in remaining.values()
                if all(d in outcomes for d in s.depends_on)
            ]

            if not ready:
                # Circular dependency or missing step
                for step in list(remaining.values()):
                    outcomes[step.step_id] = ExecutionOutcome(
                        step_id=step.step_id,
                        success=False,
                        error="Dependency could not be satisfied",
                    )
                remaining.clear()
                break

            # Execute ready steps concurrently
            tasks = [self.execute_step(s) for s in ready]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for step, result in zip(ready, batch_results):
                if isinstance(result, Exception):
                    outcomes[step.step_id] = ExecutionOutcome(
                        step_id=step.step_id,
                        success=False,
                        error=f"Unexpected error: {result}",
                    )
                else:
                    outcomes[step.step_id] = result
                del remaining[step.step_id]

        # Return in original order
        return [outcomes[s.step_id] for s in steps]

    def clear(self) -> None:
        """Clear observability traces."""
        self._observability.clear()
