"""
Workflow Run Manager (M9.10 — Runtime Workflow Engine).

Layer: Application/Core — composes the existing WorkflowEngine; it
does not replace it. The engine keeps its synchronous-await contract
(run() → WorkflowResult); this manager adds the runtime lifecycle
Milestone 9.10 requires on top:

    Run · Pause · Resume · Retry · Cancel · Timeline · Logs · Metrics

Design
------
- Each start() creates a ManagedRun and an asyncio.Task executing the
  workflow through the *shared* engine, so results also land in the
  engine's result store and the WorkflowMonitor keeps aggregating.
- Pause/resume/cancel use the engine's M9.10 ``step_gate`` hook:
  the gate awaits an asyncio.Event between steps (pause blocks it)
  and raises CancelledError when a cancel was requested. Steps are
  atomic — pause/cancel take effect at the next step boundary, which
  is the only safe semantic for arbitrary agent/tool steps.
- Retry creates a fresh run of the same workflow with the same
  variables, linked via ``retry_of`` for the timeline.
- Logs are real events recorded at every lifecycle transition and
  step boundary; nothing is fabricated.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from workflows.engine import WorkflowEngine
from workflows.models import Workflow, WorkflowResult, WorkflowState


class RunState(str, Enum):
    """Lifecycle states for a managed workflow run."""

    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RunLogEntry:
    """One timestamped event in a run's log."""

    timestamp: float
    event: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"timestamp": self.timestamp, "event": self.event, "detail": self.detail}


@dataclass
class ManagedRun:
    """Bookkeeping for one workflow run under management."""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    workflow_name: str = ""
    state: RunState = RunState.RUNNING
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    variables: dict[str, Any] = field(default_factory=dict)
    retry_of: Optional[str] = None
    result: Optional[WorkflowResult] = None
    logs: list[RunLogEntry] = field(default_factory=list)
    # internals — not serialized
    _resume_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _cancel_requested: bool = field(default=False, repr=False)
    _task: Optional[asyncio.Task] = field(default=None, repr=False)

    def log(self, event: str, detail: str = "") -> None:
        self.logs.append(RunLogEntry(timestamp=time.time(), event=event, detail=detail))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "state": self.state.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": (
                ((self.finished_at or time.time()) - self.started_at) * 1000.0
            ),
            "variables": dict(self.variables),
            "retry_of": self.retry_of,
            "result": self.result.to_dict() if self.result else None,
            "logs": [entry.to_dict() for entry in self.logs],
        }

    def timeline(self) -> list[dict[str, Any]]:
        """Merged, time-ordered view of lifecycle events + step records."""
        events: list[dict[str, Any]] = [
            {**entry.to_dict(), "kind": "lifecycle"} for entry in self.logs
        ]
        if self.result is not None:
            for record in self.result.history:
                events.append(
                    {
                        "kind": "step",
                        "timestamp": record.started_at,
                        "event": f"step:{record.step_id}",
                        "detail": (
                            "skipped"
                            if record.skipped
                            else ("succeeded" if record.success else f"failed: {record.error}")
                        ),
                        "duration_ms": record.duration_ms,
                        "attempts": record.attempts,
                    }
                )
        events.sort(key=lambda e: e["timestamp"])
        return events


class WorkflowRunManager:
    """Manage the lifecycle of workflow runs on a shared WorkflowEngine."""

    def __init__(self, engine: WorkflowEngine, max_runs: int = 500) -> None:
        if max_runs < 1:
            raise ValueError("max_runs must be >= 1")
        self._engine = engine
        self._runs: dict[str, ManagedRun] = {}
        self._max_runs = max_runs

    @property
    def engine(self) -> WorkflowEngine:
        return self._engine

    # ── Lifecycle ───────────────────────────────────────────────

    async def start(
        self,
        workflow: Workflow,
        variables: Optional[dict[str, Any]] = None,
        retry_of: Optional[str] = None,
    ) -> ManagedRun:
        """Start a workflow run as a managed background task."""
        run = ManagedRun(
            workflow_id=workflow.workflow_id,
            workflow_name=workflow.name,
            variables=dict(variables or {}),
            retry_of=retry_of,
        )
        run._resume_event.set()  # not paused initially
        run.log("started", f"workflow '{workflow.name}'")

        async def _gate(step: Any) -> None:
            if run._cancel_requested:
                raise asyncio.CancelledError()
            if not run._resume_event.is_set():
                run.log("paused_at_step", getattr(step, "step_id", ""))
            await run._resume_event.wait()
            if run._cancel_requested:
                raise asyncio.CancelledError()

        async def _execute() -> None:
            try:
                result = await self._engine.run(
                    workflow, dict(run.variables), step_gate=_gate
                )
                run.result = result
                if result.state == WorkflowState.COMPLETED:
                    run.state = RunState.COMPLETED
                    run.log("completed")
                else:
                    run.state = RunState.FAILED
                    run.log("failed", result.error or "")
            except asyncio.CancelledError:
                run.state = RunState.CANCELLED
                run.result = self._engine.get_result(workflow.workflow_id)
                run.log("cancelled")
            except Exception as exc:  # noqa: BLE001 — isolation boundary
                run.state = RunState.FAILED
                run.log("failed", f"{type(exc).__name__}: {exc}")
            finally:
                run.finished_at = time.time()

        run._task = asyncio.create_task(_execute())
        self._runs[run.run_id] = run
        self._evict_old_runs()
        return run

    async def wait(self, run_id: str, timeout: Optional[float] = None) -> ManagedRun:
        """Await a run's completion (or timeout) and return it."""
        run = self._require(run_id)
        if run._task is not None and not run._task.done():
            await asyncio.wait({run._task}, timeout=timeout)
        return run

    def pause(self, run_id: str) -> ManagedRun:
        """Pause a running workflow at the next step boundary."""
        run = self._require(run_id)
        if run.state != RunState.RUNNING:
            raise InvalidRunTransition(
                f"Cannot pause run in state '{run.state.value}'"
            )
        run._resume_event.clear()
        run.state = RunState.PAUSED
        run.log("pause_requested")
        return run

    def resume(self, run_id: str) -> ManagedRun:
        """Resume a paused workflow."""
        run = self._require(run_id)
        if run.state != RunState.PAUSED:
            raise InvalidRunTransition(
                f"Cannot resume run in state '{run.state.value}'"
            )
        run.state = RunState.RUNNING
        run._resume_event.set()
        run.log("resumed")
        return run

    def cancel(self, run_id: str) -> ManagedRun:
        """Cancel a running or paused workflow at the next step boundary."""
        run = self._require(run_id)
        if run.state not in (RunState.RUNNING, RunState.PAUSED):
            raise InvalidRunTransition(
                f"Cannot cancel run in state '{run.state.value}'"
            )
        run._cancel_requested = True
        run._resume_event.set()  # unblock a paused gate so it can cancel
        run.log("cancel_requested")
        return run

    async def retry(self, run_id: str, workflow: Workflow) -> ManagedRun:
        """Start a fresh run of a finished run's workflow.

        The caller supplies the workflow definition (the manager
        stores runs, not definitions — the registry owns those).
        """
        source = self._require(run_id)
        if source.state in (RunState.RUNNING, RunState.PAUSED):
            raise InvalidRunTransition(
                "Cannot retry a run that is still in progress"
            )
        return await self.start(
            workflow, variables=source.variables, retry_of=run_id
        )

    # ── Introspection ───────────────────────────────────────────

    def get(self, run_id: str) -> Optional[ManagedRun]:
        return self._runs.get(run_id)

    def list_runs(self, state: Optional[RunState] = None) -> list[ManagedRun]:
        """All managed runs, newest first, optionally filtered."""
        runs = sorted(
            self._runs.values(), key=lambda r: r.started_at, reverse=True
        )
        if state is not None:
            runs = [r for r in runs if r.state == state]
        return runs

    def get_metrics(self) -> dict[str, Any]:
        """Aggregate metrics across all managed runs."""
        runs = list(self._runs.values())
        finished = [r for r in runs if r.finished_at is not None]
        durations = [
            (r.finished_at - r.started_at) * 1000.0 for r in finished
        ]
        return {
            "total_runs": len(runs),
            "running": sum(1 for r in runs if r.state == RunState.RUNNING),
            "paused": sum(1 for r in runs if r.state == RunState.PAUSED),
            "completed": sum(1 for r in runs if r.state == RunState.COMPLETED),
            "failed": sum(1 for r in runs if r.state == RunState.FAILED),
            "cancelled": sum(1 for r in runs if r.state == RunState.CANCELLED),
            "retries": sum(1 for r in runs if r.retry_of is not None),
            "avg_duration_ms": (sum(durations) / len(durations)) if durations else 0.0,
        }

    def clear(self) -> None:
        """Drop finished runs (in-progress runs are kept)."""
        self._runs = {
            rid: r
            for rid, r in self._runs.items()
            if r.state in (RunState.RUNNING, RunState.PAUSED)
        }

    # ── Internals ───────────────────────────────────────────────

    def _require(self, run_id: str) -> ManagedRun:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"Run '{run_id}' not found")
        return run

    def _evict_old_runs(self) -> None:
        if len(self._runs) <= self._max_runs:
            return
        finished = [
            r
            for r in sorted(self._runs.values(), key=lambda r: r.started_at)
            if r.state not in (RunState.RUNNING, RunState.PAUSED)
        ]
        excess = len(self._runs) - self._max_runs
        for run in finished[:excess]:
            del self._runs[run.run_id]


class InvalidRunTransition(Exception):
    """Raised for lifecycle operations invalid in the current state."""
