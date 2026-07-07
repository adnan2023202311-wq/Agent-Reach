"""
Workflow & Orchestration Layer — Workflow Models (M5.1).

Layer: Application/Core — depends inward on domain/ only.

Defines the data model for the higher-level Workflow & Orchestration
Layer introduced in Milestone 5. These models describe NAMED
workflows that orchestrate agents and tools — distinct from the
lower-level capability-driven DAG WorkflowEngine implemented in
Milestone 4 (workflow/engine.py), which remains untouched.

Provided types:
- StepType:               enum of step kinds (AGENT, TOOL)
- WorkflowState:          lifecycle states for a workflow run
- Condition / ConditionOp: structured conditional expressions
- WorkflowStep:           a single step in a workflow
- Workflow:               a named workflow definition
- WorkflowContext:        runtime state carried through execution
- StepExecutionRecord:    one step's outcome inside the history
- WorkflowResult:         final outcome of a workflow run

All models are pure data; they do not perform I/O. Validation and
execution live in workflows/validation.py and workflows/engine.py
respectively.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from domain.models import RetryPolicy


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StepType(str, Enum):
    """The kind of work a WorkflowStep performs."""

    AGENT = "agent"
    TOOL = "tool"


class WorkflowState(str, Enum):
    """Finite state machine for a Workflow run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConditionOp(str, Enum):
    """Supported comparison operators for structured conditions.

    A condition of the form ``{"variable": "variables.x", "op": "==",
    "value": 5}`` is evaluated against the WorkflowContext at
    execution time. ``TRUTHY`` / ``FALSY`` ignore ``value``.
    """

    EQ = "=="
    NE = "!="
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
    IN = "in"
    NOT_IN = "not_in"
    TRUTHY = "truthy"
    FALSY = "falsy"


# ---------------------------------------------------------------------------
# Condition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Condition:
    """Structured conditional expression.

    Attributes:
        variable: dotted path resolved against a WorkflowContext,
            e.g. ``"variables.user_name"`` or ``"outputs.step_a.text"``.
        op: comparison operator.
        value: value to compare against (ignored for TRUTHY/FALSY).
    """

    variable: str
    op: ConditionOp
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {"variable": self.variable, "op": self.op.value, "value": self.value}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Condition:
        """Deserialize from a dict. Raises ``ValueError`` on invalid input."""
        if not isinstance(data, dict):
            raise ValueError(f"Condition must be a dict, got {type(data).__name__}")
        for key in ("variable", "op"):
            if key not in data:
                raise ValueError(f"Condition missing required key: {key!r}")
        try:
            op = ConditionOp(data["op"])
        except ValueError as exc:
            raise ValueError(f"Unknown ConditionOp: {data['op']!r}") from exc
        return cls(variable=data["variable"], op=op, value=data.get("value"))


# ---------------------------------------------------------------------------
# WorkflowStep
# ---------------------------------------------------------------------------


@dataclass
class WorkflowStep:
    """A single step in a Workflow.

    A step targets either a registered ``AgentType`` (when ``type`` is
    ``AGENT``) or a registered tool name (when ``type`` is ``TOOL``).

    Attributes:
        step_id: unique identifier within the workflow.
        name:    human-readable name (for display/logging).
        type:    AGENT or TOOL.
        target:  the AgentType value (string) or tool name to invoke.
        inputs:  parameter mapping; values may contain ``{{ }}``
            template expressions resolved against the context.
        condition: optional Condition — when present, the step is
            skipped unless the condition evaluates true.
        depends_on: step_ids that must complete before this one.
        retry_policy: optional retry policy; defaults to the
            Workflow's policy when omitted.
        output_keys: named output keys produced by this step,
            recorded under ``context.step_outputs[step_id]``.
        timeout_seconds: per-step timeout (advisory; the executor
            enforces its own timeout for tool calls).
    """

    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    type: StepType = StepType.AGENT
    target: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    condition: Optional[Condition] = None
    depends_on: list[str] = field(default_factory=list)
    retry_policy: Optional[RetryPolicy] = None
    output_keys: list[str] = field(default_factory=list)
    timeout_seconds: float = 30.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "type": self.type.value,
            "target": self.target,
            "inputs": dict(self.inputs),
            "condition": self.condition.to_dict() if self.condition else None,
            "depends_on": list(self.depends_on),
            "retry_policy": (
                {
                    "max_attempts": self.retry_policy.max_attempts,
                    "backoff_seconds": self.retry_policy.backoff_seconds,
                    "timeout_seconds": self.retry_policy.timeout_seconds,
                }
                if self.retry_policy is not None
                else None
            ),
            "output_keys": list(self.output_keys),
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        """Deserialize from a dict. Raises ``ValueError`` on invalid input."""
        if not isinstance(data, dict):
            raise ValueError(f"WorkflowStep must be a dict, got {type(data).__name__}")
        if "type" in data:
            try:
                step_type = StepType(data["type"])
            except ValueError as exc:
                raise ValueError(f"Unknown StepType: {data['type']!r}") from exc
        else:
            step_type = StepType.AGENT

        retry_policy: Optional[RetryPolicy] = None
        if data.get("retry_policy") is not None:
            rp = data["retry_policy"]
            retry_policy = RetryPolicy(
                max_attempts=int(rp.get("max_attempts", 3)),
                backoff_seconds=float(rp.get("backoff_seconds", 1.5)),
                timeout_seconds=float(rp.get("timeout_seconds", 120.0)),
            )

        condition: Optional[Condition] = None
        if data.get("condition") is not None:
            condition = Condition.from_dict(data["condition"])

        return cls(
            step_id=str(data.get("step_id") or uuid.uuid4()),
            name=str(data.get("name", "")),
            type=step_type,
            target=str(data.get("target", "")),
            inputs=dict(data.get("inputs") or {}),
            condition=condition,
            depends_on=list(data.get("depends_on") or []),
            retry_policy=retry_policy,
            output_keys=list(data.get("output_keys") or []),
            timeout_seconds=float(data.get("timeout_seconds", 30.0)),
        )


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


@dataclass
class Workflow:
    """A named Workflow definition.

    A Workflow is a reusable, persisted, validatable description of
    how to coordinate one or more agents and tools to produce a set
    of named outputs.

    Attributes:
        workflow_id: unique identifier.
        name: human-readable name (must be unique within a Registry).
        description: optional longer description.
        metadata: arbitrary metadata (tags, owner, version, ...).
        variables: initial variable values; templates in inputs and
            outputs resolve against these.
        steps: ordered list of WorkflowSteps.
        outputs: named outputs the workflow produces. Each entry maps
            an output name to a dotted path of the form
            ``"variables.x"`` or ``"outputs.step_id.key"``.
        default_retry_policy: applied to steps that don't override it.
        version: schema/workflow version, useful for migrations.
        created_at: epoch seconds when the workflow was registered.
    """

    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    steps: list[WorkflowStep] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)
    default_retry_policy: Optional[RetryPolicy] = None
    version: str = "1.0"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "metadata": dict(self.metadata),
            "variables": dict(self.variables),
            "steps": [s.to_dict() for s in self.steps],
            "outputs": dict(self.outputs),
            "default_retry_policy": (
                {
                    "max_attempts": self.default_retry_policy.max_attempts,
                    "backoff_seconds": self.default_retry_policy.backoff_seconds,
                    "timeout_seconds": self.default_retry_policy.timeout_seconds,
                }
                if self.default_retry_policy is not None
                else None
            ),
            "version": self.version,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workflow:
        """Deserialize from a dict. Raises ``ValueError`` on invalid input."""
        if not isinstance(data, dict):
            raise ValueError(f"Workflow must be a dict, got {type(data).__name__}")

        default_rp: Optional[RetryPolicy] = None
        if data.get("default_retry_policy") is not None:
            rp = data["default_retry_policy"]
            default_rp = RetryPolicy(
                max_attempts=int(rp.get("max_attempts", 3)),
                backoff_seconds=float(rp.get("backoff_seconds", 1.5)),
                timeout_seconds=float(rp.get("timeout_seconds", 120.0)),
            )

        steps_raw = data.get("steps") or []
        steps = [WorkflowStep.from_dict(s) for s in steps_raw]

        return cls(
            workflow_id=str(data.get("workflow_id") or uuid.uuid4()),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            metadata=dict(data.get("metadata") or {}),
            variables=dict(data.get("variables") or {}),
            steps=steps,
            outputs=dict(data.get("outputs") or {}),
            default_retry_policy=default_rp,
            version=str(data.get("version", "1.0")),
            created_at=float(data.get("created_at", time.time())),
        )


# ---------------------------------------------------------------------------
# WorkflowContext
# ---------------------------------------------------------------------------


@dataclass
class WorkflowContext:
    """Runtime state carried through workflow execution.

    A fresh context is built from ``Workflow.variables`` at the start
    of every run. Steps record their outputs under
    ``step_outputs[step_id]`` and may push derived values into
    ``variables``. The execution history captures every step attempt
    in order.

    Attributes:
        workflow_id: the workflow being executed.
        variables:    mutable variable bag (templates resolve against it).
        step_outputs: per-step output dicts, keyed by step_id.
        metadata:     arbitrary metadata (run id, start time, ...).
        history:      ordered StepExecutionRecords.
    """

    workflow_id: str
    variables: dict[str, Any] = field(default_factory=dict)
    step_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    history: list[StepExecutionRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# StepExecutionRecord
# ---------------------------------------------------------------------------


@dataclass
class StepExecutionRecord:
    """One step's outcome inside the execution history.

    A record is appended for every step attempt — successful or
    failed — so the WorkflowContext's history gives a full audit
    trail of what actually happened during a run.
    """

    step_id: str
    step_name: str
    step_type: StepType
    started_at: float
    finished_at: float
    duration_ms: float
    success: bool
    skipped: bool = False
    attempts: int = 1
    output: Any = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# WorkflowResult
# ---------------------------------------------------------------------------


@dataclass
class WorkflowResult:
    """Final outcome of a Workflow run.

    Attributes:
        workflow_id: the workflow that was executed.
        state:       terminal lifecycle state.
        outputs:     resolved workflow outputs (by name).
        history:     every StepExecutionRecord produced.
        duration_ms: total wall-clock duration of the run.
        error:       human-readable error message if FAILED.
        started_at:  epoch seconds when execution began.
        finished_at: epoch seconds when execution ended.
    """

    workflow_id: str
    state: WorkflowState
    outputs: dict[str, Any] = field(default_factory=dict)
    history: list[StepExecutionRecord] = field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    finished_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict.

        ``history`` records are flattened to plain dicts; ``output``
        payloads are kept verbatim (callers are responsible for
        putting JSON-friendly values there if they want to persist).
        """
        return {
            "workflow_id": self.workflow_id,
            "state": self.state.value,
            "outputs": dict(self.outputs),
            "history": [
                {
                    "step_id": r.step_id,
                    "step_name": r.step_name,
                    "step_type": r.step_type.value,
                    "started_at": r.started_at,
                    "finished_at": r.finished_at,
                    "duration_ms": r.duration_ms,
                    "success": r.success,
                    "skipped": r.skipped,
                    "attempts": r.attempts,
                    "output": r.output,
                    "error": r.error,
                }
                for r in self.history
            ],
            "duration_ms": self.duration_ms,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowResult:
        """Deserialize from a dict. Raises ``ValueError`` on invalid input."""
        if not isinstance(data, dict):
            raise ValueError(f"WorkflowResult must be a dict, got {type(data).__name__}")
        try:
            state = WorkflowState(data.get("state", "completed"))
        except ValueError as exc:
            raise ValueError(f"Unknown WorkflowState: {data.get('state')!r}") from exc

        history: list[StepExecutionRecord] = []
        for r in data.get("history") or []:
            history.append(
                StepExecutionRecord(
                    step_id=str(r["step_id"]),
                    step_name=str(r.get("step_name", "")),
                    step_type=StepType(r.get("step_type", StepType.AGENT.value)),
                    started_at=float(r["started_at"]),
                    finished_at=float(r["finished_at"]),
                    duration_ms=float(r["duration_ms"]),
                    success=bool(r["success"]),
                    skipped=bool(r.get("skipped", False)),
                    attempts=int(r.get("attempts", 1)),
                    output=r.get("output"),
                    error=r.get("error"),
                )
            )

        return cls(
            workflow_id=str(data["workflow_id"]),
            state=state,
            outputs=dict(data.get("outputs") or {}),
            history=history,
            duration_ms=float(data.get("duration_ms", 0.0)),
            error=data.get("error"),
            started_at=float(data.get("started_at", time.time())),
            finished_at=float(data.get("finished_at", time.time())),
        )
