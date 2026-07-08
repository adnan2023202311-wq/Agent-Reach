"""
API layer: request/response schemas.

Layer: Interface/Presentation.

ChatResponse reuses domain.models.AgentResult directly instead of
duplicating it field-for-field into a separate DTO class — pydantic
already serializes AgentResult's enum fields (AgentType, TaskStatus)
to plain JSON strings since both are `str, Enum` subclasses, so there
was no format mismatch a DTO was bridging. A hand-written
AgentResultDTO here would have been a class that only re-declared
another class's fields.

ChatResponse still exists as its own type rather than returning
TaskExecutionOutcome directly, for one concrete reason: `session_id`
belongs to the request, not the domain outcome, and has to be merged
in somewhere. Four fields, one real reason — if that reason goes away,
so should this class.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from domain.models import AgentResult, TaskExecutionOutcome


class ChatRequest(BaseModel):
    """What a client sends to POST /api/v1/chat."""

    message: str = Field(..., min_length=1, description="The user's request")
    session_id: Optional[str] = None
    context: dict[str, Any] = Field(default_factory=dict)


class AgentSummary(BaseModel):
    """What GET /api/v1/agents reports for one registered agent.

    Presentation-only fields the frontend needs (icon, tint color) are
    deliberately absent — those are static per-id lookups the frontend
    already owns (see frontend/src/services/http/index.ts). This only
    reports what the backend actually knows.
    """

    id: str
    name: str
    description: str
    status: str
    enabled: bool
    provider_id: Optional[str] = None
    model_id: Optional[str] = None
    system_prompt: str = ""
    max_tokens: int = 0


class ProviderSummary(BaseModel):
    """What GET /api/v1/providers reports for one known provider.

    No `apiKey` field, masked or otherwise: echoing secret material
    back over an endpoint with no authentication yet (see
    docs/ARCHITECTURE.md, recommended next milestone) isn't worth it
    for a status badge that doesn't need it.
    """

    id: str
    status: str
    enabled: bool


class DashboardSnapshot(BaseModel):
    """What GET /api/v1/dashboard reports.

    `activity` and `recent_chats` are honestly empty — neither usage
    metrics nor conversation history are persisted yet (InMemoryStore
    isn't wired into MainController). Real zeros, not fabricated ones.
    """

    activity: list[dict[str, Any]] = Field(default_factory=list)
    recent_chats: list[dict[str, Any]] = Field(default_factory=list)
    active_agents: list[AgentSummary] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """What POST /api/v1/chat returns.

    M9.3 addition: ``request_id`` links the response to its persisted
    execution trace (GET /api/v1/observatory/trace/{request_id}), and
    ``trace`` optionally embeds the full per-stage breakdown so the
    frontend can render the execution timeline without a second call.
    Both are None when the request bypassed the IntelligentPipeline
    (controller fallback path) — real absence, not fabricated data.
    """

    session_id: Optional[str]
    plan_id: str
    status: str
    answer: str
    results: list[AgentResult]
    request_id: Optional[str] = None
    trace: Optional[dict[str, Any]] = None

    @classmethod
    def from_outcome(
        cls,
        outcome: TaskExecutionOutcome,
        session_id: Optional[str],
        request_id: Optional[str] = None,
        trace: Optional[dict[str, Any]] = None,
    ) -> "ChatResponse":
        return cls(
            session_id=session_id,
            plan_id=outcome.plan.id,
            status=outcome.status.value,
            answer=outcome.answer,
            results=outcome.results,
            request_id=request_id,
            trace=trace,
        )
