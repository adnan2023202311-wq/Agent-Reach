"""
Workflow & Orchestration Layer — Monitoring (M5.8).

Layer: Application/Core — depends inward on domain/ only.

In-process workflow runtime statistics. Per the M5 specification:

> Track:
> - workflow duration
> - workflow failures
> - completed workflows
> - active workflows
> - execution statistics

This module is a thin, in-memory aggregator. It does not
persist metrics to disk; that belongs to a future milestone.
What it does provide is a lightweight interface that the
WorkflowEngine (or any caller) can push results into, plus
a snapshot for monitoring UIs / dashboards.

Design:
- :class:`WorkflowMonitor` is a singleton-style object. Build one
  per process; share it between the engine and any monitoring
  code that needs to read stats.
- ``record(result)`` is the only mutating method — the engine
  pushes one entry per Workflow run, regardless of outcome.
- Snapshot methods (``get_stats``, ``get_durations``, etc.) are
  read-only and safe to call from any thread/coroutine.
- All numbers are derived on demand from the underlying result
  list; nothing is pre-aggregated so there is no chance of
  counters drifting out of sync with the source of truth.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Optional

from workflows.models import WorkflowResult, WorkflowState


@dataclass
class WorkflowStats:
    """Point-in-time snapshot of workflow execution statistics."""

    total: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    active: int = 0
    """Currently running — populated when the engine signals start/end
    via :meth:`WorkflowMonitor.mark_active` /
    :meth:`WorkflowMonitor.mark_done`."""
    average_duration_ms: float = 0.0
    median_duration_ms: float = 0.0
    min_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    by_workflow: dict[str, int] = field(default_factory=dict)
    """Run count per workflow.workflow_id."""


class WorkflowMonitor:
    """Aggregate Workflow execution statistics."""

    def __init__(self) -> None:
        self._results: list[WorkflowResult] = []
        self._active: set[str] = set()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def record(self, result: WorkflowResult) -> None:
        """Append a finalized WorkflowResult to the monitor's history."""
        self._results.append(result)
        # Recording a result also ends any active tracking for
        # this workflow id.
        self._active.discard(result.workflow_id)

    def mark_active(self, workflow_id: str) -> None:
        """Record that ``workflow_id`` has started running."""
        self._active.add(workflow_id)

    def mark_done(self, workflow_id: str) -> None:
        """Record that ``workflow_id`` has finished (success or failure)."""
        self._active.discard(workflow_id)

    def clear(self) -> None:
        """Drop all recorded results and active tracking. For testing."""
        self._results.clear()
        self._active.clear()

    # ------------------------------------------------------------------
    # Read-only accessors
    # ------------------------------------------------------------------

    def get_stats(self) -> WorkflowStats:
        """Return a point-in-time WorkflowStats snapshot."""
        durations = [r.duration_ms for r in self._results]
        completed = sum(
            1 for r in self._results if r.state == WorkflowState.COMPLETED
        )
        failed = sum(
            1 for r in self._results if r.state == WorkflowState.FAILED
        )
        cancelled = sum(
            1 for r in self._results if r.state == WorkflowState.CANCELLED
        )
        return WorkflowStats(
            total=len(self._results),
            completed=completed,
            failed=failed,
            cancelled=cancelled,
            active=len(self._active),
            average_duration_ms=(
                statistics.fmean(durations) if durations else 0.0
            ),
            median_duration_ms=(
                statistics.median(durations) if durations else 0.0
            ),
            min_duration_ms=min(durations) if durations else 0.0,
            max_duration_ms=max(durations) if durations else 0.0,
            by_workflow=dict(Counter(r.workflow_id for r in self._results)),
        )

    def get_durations(self) -> list[float]:
        """Return the per-run duration list (milliseconds)."""
        return [r.duration_ms for r in self._results]

    def get_failures(self) -> list[WorkflowResult]:
        """Return every FAILED WorkflowResult in recorded order."""
        return [r for r in self._results if r.state == WorkflowState.FAILED]

    def get_completed(self) -> list[WorkflowResult]:
        """Return every COMPLETED WorkflowResult in recorded order."""
        return [r for r in self._results if r.state == WorkflowState.COMPLETED]

    def get_active(self) -> list[str]:
        """Return the workflow_ids currently marked active."""
        return sorted(self._active)

    def get_results(
        self,
        state: Optional[WorkflowState] = None,
        workflow_id: Optional[str] = None,
    ) -> list[WorkflowResult]:
        """Return results filtered by ``state`` and/or ``workflow_id``."""
        results: Iterable[WorkflowResult] = self._results
        if state is not None:
            results = [r for r in results if r.state == state]
        if workflow_id is not None:
            results = [r for r in results if r.workflow_id == workflow_id]
        return list(results)


__all__ = ["WorkflowMonitor", "WorkflowStats"]
