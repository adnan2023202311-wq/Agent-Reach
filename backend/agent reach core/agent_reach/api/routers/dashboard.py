"""
API layer: /api/v1/dashboard.

Layer: Interface/Presentation.

Composes the same real agent data as /api/v1/agents (filtered to
enabled ones) with honestly-empty activity stats and recent-chat
history — neither is persisted anywhere yet. This endpoint doesn't
introduce a new "dashboard aggregation" concept in core/; it's a thin
API-layer view over data that already exists elsewhere, which is why
it lives here rather than as a new domain/core abstraction.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_controller
from api.routers.agents import summarize_agent
from api.schemas import DashboardSnapshot
from config.settings import Settings, get_settings
from core.controller import MainController

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardSnapshot)
async def get_dashboard(
    controller: MainController = Depends(get_controller),
    settings: Settings = Depends(get_settings),
) -> DashboardSnapshot:
    agents = [summarize_agent(t, settings) for t in controller.registered_agent_types()]
    return DashboardSnapshot(
        activity=[],
        recent_chats=[],
        active_agents=[a for a in agents if a.enabled],
        tools=[],
    )
