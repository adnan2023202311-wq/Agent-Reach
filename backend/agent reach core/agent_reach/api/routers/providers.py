"""
API layer: /api/v1/providers.

Layer: Interface/Presentation.

Reports which of config.settings.KNOWN_PROVIDERS are actually usable —
today, that's only ever "anthropic" (the one provider with a working
ModelClient — see domain/interfaces.py's ModelClient docstring for why
a real multi-provider router doesn't exist yet). A provider with a key
set in .env but no client implementation is still reported
"unconfigured": the key alone can't do anything.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.schemas import ProviderSummary
from config.settings import KNOWN_PROVIDERS, Settings, get_settings

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


@router.get("", response_model=list[ProviderSummary])
async def list_providers(settings: Settings = Depends(get_settings)) -> list[ProviderSummary]:
    return [
        ProviderSummary(
            id=provider_id,
            status="ready" if settings.is_provider_ready(provider_id) else "unconfigured",
            enabled=settings.is_provider_ready(provider_id),
        )
        for provider_id in KNOWN_PROVIDERS
    ]


@router.patch("/{provider_id}")
async def update_provider(provider_id: str) -> None:
    """Not implemented — provider credentials come from environment
    variables (config/settings.py), which this process can't rewrite
    at runtime. Changing a key means editing .env and restarting, not
    a PATCH request. See api/routers/agents.py's update_agent for the
    same "don't fake persistence" reasoning."""
    raise HTTPException(
        status_code=501,
        detail={
            "message": "Provider credentials are set via environment variables, not the API.",
            "code": "NOT_IMPLEMENTED",
        },
    )
