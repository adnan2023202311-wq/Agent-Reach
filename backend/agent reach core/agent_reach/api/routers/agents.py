"""
API layer: /api/v1/agents — reports the agents actually registered
with MainController, not the Blueprint's full nine-agent roster.

Layer: Interface/Presentation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agents.research_agent import SYSTEM_PROMPT as RESEARCH_SYSTEM_PROMPT
from api.dependencies import get_controller
from api.schemas import AgentSummary
from config.settings import Settings, get_settings
from core.controller import MainController
from domain.models import AgentType

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

# Static per-agent-type presentation metadata. A dict this small, for
# two entries, doesn't need its own module or a domain-level "agent
# registry with self-reporting status" — that's worth building once a
# third or fourth real agent makes a flat dict unwieldy, not now.
_METADATA: dict[AgentType, dict[str, object]] = {
    AgentType.RESEARCH: {
        "name": "Research Agent",
        "description": "Answers questions using the configured model. No live web search yet.",
        "status": "ready",
        "enabled": True,
        "system_prompt": RESEARCH_SYSTEM_PROMPT,
        "max_tokens": 1024,
    },
    AgentType.CODING: {
        "name": "Coding Agent",
        "description": "Reads, writes and refactors code across a repository.",
        "status": "needs_config",
        "enabled": False,
        "system_prompt": "",
        "max_tokens": 0,
    },
}
_FALLBACK_METADATA: dict[str, object] = {
    "name": "",
    "description": "Registered but not yet described.",
    "status": "needs_config",
    "enabled": False,
    "system_prompt": "",
    "max_tokens": 0,
}

# Only ResearchAgent is wired to a real ModelClient today (see
# domain/interfaces.py's ModelClient docstring) — this is what decides
# whether provider_id/model_id are reported or left null.
_AGENTS_WITH_MODEL_CLIENT = {AgentType.RESEARCH}


def summarize_agent(agent_type: AgentType, settings: Settings) -> AgentSummary:
    """Public (not underscore-prefixed): reused by api/routers/dashboard.py
    so dashboard data stays a thin view over this router's data rather
    than a second, possibly-diverging implementation."""
    meta = _METADATA.get(agent_type, _FALLBACK_METADATA)
    has_model = agent_type in _AGENTS_WITH_MODEL_CLIENT
    return AgentSummary(
        id=agent_type.value,
        name=meta["name"] or agent_type.value.replace("_", " ").title(),
        description=meta["description"],
        status=meta["status"],
        enabled=meta["enabled"],
        provider_id=settings.default_model_provider if has_model else None,
        model_id=settings.default_model if has_model else None,
        system_prompt=meta["system_prompt"],
        max_tokens=meta["max_tokens"],
    )


@router.get("", response_model=list[AgentSummary])
async def list_agents(
    controller: MainController = Depends(get_controller),
    settings: Settings = Depends(get_settings),
) -> list[AgentSummary]:
    return [summarize_agent(t, settings) for t in controller.registered_agent_types()]


@router.patch("/{agent_id}")
async def update_agent(agent_id: str) -> None:
    """Not implemented on purpose.

    No persistence layer exists for agent configuration — agents are
    wired once in composition.py, not stored anywhere mutable. The
    current frontend doesn't call this either (its "Configure" sheet
    edits local component state only, confirmed by inspection). Kept
    honest rather than faking a save that reverts on refresh.
    """
    raise HTTPException(
        status_code=501,
        detail={
            "message": "Editing agent configuration isn't supported yet.",
            "code": "NOT_IMPLEMENTED",
        },
    )
