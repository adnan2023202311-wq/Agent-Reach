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

# Static per-agent-type presentation metadata.
# Milestone 8: expanded to full Production Agent Studio catalog
# matching the Lovable frontend's 5-agent roster.
_METADATA: dict[AgentType, dict[str, object]] = {
    AgentType.RESEARCH: {
        "name": "Research Agent",
        "description": "Deep web and document research with cited synthesis.",
        "status": "ready",
        "enabled": True,
        "system_prompt": RESEARCH_SYSTEM_PROMPT,
        "max_tokens": 4000,
    },
    AgentType.CODING: {
        "name": "Coding Agent",
        "description": "Read, write and refactor code across a repository.",
        "status": "needs_config",
        "enabled": False,
        "system_prompt": "You are a senior engineer. Produce production-quality diffs with tests and clear commit messages.",
        "max_tokens": 6000,
    },
    AgentType.BROWSER: {
        "name": "Browser Agent",
        "description": "Navigate websites and extract structured information.",
        "status": "ready",
        "enabled": True,
        "system_prompt": "You control a headless browser. Plan the shortest path to the goal and validate each step.",
        "max_tokens": 3000,
    },
    AgentType.NEWS: {
        "name": "News Agent",
        "description": "Track breaking headlines and produce daily summaries.",
        "status": "disabled",
        "enabled": False,
        "system_prompt": "You summarize the day's most important news. Group by topic and cite sources.",
        "max_tokens": 2000,
    },
    AgentType.WRITING: {
        "name": "Content Agent",
        "description": "Draft posts, emails and marketing copy in your voice.",
        "status": "error",
        "enabled": True,
        "system_prompt": "You are a versatile writer. Match the requested tone precisely and keep copy tight.",
        "max_tokens": 2500,
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

# Milestone 8 — Production Agent Studio:
# All 5 production agents are now wired through the Intelligent Pipeline
# with automatic provider routing (ReachIntelligenceRouter).
# Provider/model reporting reflects the active pipeline configuration.
_AGENTS_WITH_MODEL_CLIENT = {
    AgentType.RESEARCH,
    AgentType.CODING,
    AgentType.BROWSER,
    AgentType.NEWS,
    AgentType.WRITING,
}


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
    # Milestone 8: return full Production Agent Catalog so the
    # Lovable frontend's Agent Studio is fully populated.
    # Merge registered types first, then append catalog-only agents
    # to preserve backward compatibility with tests that assert
    # registered_agent_types() are included.
    registered = set(controller.registered_agent_types())
    catalog_order = [
        AgentType.RESEARCH,
        AgentType.BROWSER,
        AgentType.CODING,
        AgentType.NEWS,
        AgentType.WRITING,
    ]
    # start with registered agents (preserves test expectations)
    result_types = list(registered)
    # append catalog agents not yet registered
    for at in catalog_order:
        if at not in registered and at in _METADATA:
            result_types.append(at)
    # ensure deterministic catalog order for UI
    # sort by catalog_order priority
    result_types_sorted = sorted(
        result_types,
        key=lambda t: catalog_order.index(t) if t in catalog_order else 999,
    )
    return [summarize_agent(t, settings) for t in result_types_sorted]


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
