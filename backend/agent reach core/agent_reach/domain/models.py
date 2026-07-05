"""
Domain layer: enums, entities, and value objects.

Layer: Domain (innermost — no imports from core/, agents/,
infrastructure/, api/, or config/).

Enums and entities used to live in separate files (enums.py,
entities.py). Merged here because nothing ever imports one without the
other — every entity is built from these enums, and every consumer of
an enum is also a consumer of the entity that carries it. Splitting
them bought no isolation, only an extra file to open.

Design note — immutability:
Every entity below is frozen. A SubTask is created once by a Planner
and never mutated; execution outcome is captured separately in a new
AgentResult. This matters the moment independent subtasks are
dispatched concurrently (SubTask.depends_on exists for this, not yet
used) — mutating one shared object from multiple coroutines would be a
race condition. Freezing costs nothing extra (it's a pydantic config
flag) and removes that failure mode before it can exist.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class AgentType(str, Enum):
    """Every specialized agent kind described in Blueprint Section 9."""

    RESEARCH = "research"
    CODING = "coding"
    BROWSER = "browser"
    NEWS = "news"
    WRITING = "writing"
    IMAGE = "image"
    PLANNING = "planning"
    MEMORY = "memory"
    SOCIAL_MEDIA = "social_media"


class TaskStatus(str, Enum):
    """Terminal outcome of a dispatched SubTask."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SubTask(BaseModel):
    """A single unit of work assigned to exactly one agent type."""

    model_config = {"frozen": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_type: AgentType
    description: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    """IDs of subtasks that must finish first. Defined but not yet
    honored — MainController currently runs subtasks in list order.
    See docs/ARCHITECTURE.md, "Remaining weaknesses"."""


class TaskPlan(BaseModel):
    """The full set of subtasks a Planner produced for one user request."""

    model_config = {"frozen": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_request: str
    subtasks: list[SubTask] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentResult(BaseModel):
    """Outcome of dispatching one SubTask to its agent.

    `status` is the single source of truth for success/failure; there
    is no separate boolean flag that could disagree with it.
    """

    model_config = {"frozen": True}

    subtask_id: str
    agent_type: AgentType
    status: TaskStatus
    attempts: int
    output: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None

    @property
    def success(self) -> bool:
        return self.status == TaskStatus.SUCCEEDED


class TaskExecutionOutcome(BaseModel):
    """Everything the Main Controller produced for one user request."""

    model_config = {"frozen": True}

    plan: TaskPlan
    results: list[AgentResult]
    answer: str
    status: TaskStatus


@dataclass(frozen=True)
class RetryPolicy:
    """How AgentDispatcher retries a failing subtask.

    A plain dataclass, not a pydantic model — it's always built
    programmatically (from Settings, or directly in tests), never
    parsed from external input, so no validation machinery is needed.
    """

    max_attempts: int = 3
    backoff_seconds: float = 1.5
    timeout_seconds: float = 120.0
