"""
API layer: /api/v1/providers.

Layer: Interface/Presentation.

M9.5 — Live Provider Runtime. The M8 version reported only a
configured/unconfigured flag. This version exposes production runtime
information per provider, every field sourced from a live component:

- configuration state  → config.settings (env keys)
- health / latency /
  success rate         → ReachIntelligenceRouter provider stats
                          (recorded from real routing decisions)
- usage                → persisted pipeline traces (M9.3 trace store)
- token usage          → context tokens from those traces
- cost estimation      → router cost model × usage (explicitly an
                          estimate — labeled as such)
- capabilities /models → router capability sets + ProviderManager
                          default model mapping

The GET list keeps the original ProviderSummary fields for backward
compatibility and adds the runtime block.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_pipeline
from api.schemas import ProviderSummary
from config.settings import KNOWN_PROVIDERS, Settings, get_settings

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


# Router capability names use "gemini"/"google" inconsistently across
# the config and routing layers; normalize here at the boundary.
# NOTE: settings "groq" (the inference company) and router "grok"
# (xAI's model) are different providers — deliberately NOT mapped.
_SETTINGS_TO_ROUTER: dict[str, str] = {"google": "gemini"}
_ROUTER_TO_SETTINGS: dict[str, str] = {"gemini": "google"}


def _router_name(provider_id: str) -> str:
    return _SETTINGS_TO_ROUTER.get(provider_id, provider_id)


def _all_provider_ids(pipeline: Any) -> list[str]:
    """Union of config-known providers and router-known providers.

    M9.5 requires *every* provider to expose production information —
    including router-only ones like ollama/grok that need no settings
    key. Router names are normalized to settings names where the two
    layers refer to the same provider.
    """
    ids = list(KNOWN_PROVIDERS)
    if pipeline is not None:
        try:
            router_obj = pipeline._get_router()
            for name in router_obj.list_providers():
                normalized = _ROUTER_TO_SETTINGS.get(name, name)
                if normalized not in ids:
                    ids.append(normalized)
        except Exception:
            pass
    return ids


def _default_model(provider_id: str) -> str:
    from infrastructure.provider_manager import _DEFAULT_MODELS

    return _DEFAULT_MODELS.get(_router_name(provider_id), "")


def _provider_runtime(
    provider_id: str, pipeline: Any, settings: Settings
) -> dict[str, Any]:
    """Assemble the live runtime block for one provider."""
    rid = _router_name(provider_id)

    health: dict[str, Any] = {
        "healthy": True,
        "success_rate": 1.0,
        "avg_latency_ms": 0,
        "total_calls": 0,
        "last_error": "",
    }
    capabilities: list[str] = []
    cost_per_1k = 0.0
    usage = 0
    token_usage = 0

    if pipeline is not None:
        try:
            router_obj = pipeline._get_router()
            health = router_obj.get_provider_health().get(rid, health)
            capabilities = sorted(
                c.value for c in router_obj.get_capabilities(rid)
            )
            cost_per_1k = router_obj.get_cost(rid)
        except Exception:
            pass
        try:
            for trace in pipeline.list_traces(limit=pipeline.trace_store.max_traces):
                if trace.router_provider == rid:
                    usage += 1
                    token_usage += trace.context_tokens_used
        except Exception:
            pass

    configured = settings.is_provider_ready(provider_id)
    return {
        "configured": configured,
        "available": configured and health.get("healthy", True),
        "default_model": _default_model(provider_id),
        "capabilities": capabilities,
        "health": health,
        "usage": {
            "requests": usage,
            "tokens": token_usage,
        },
        "cost": {
            "per_1k_tokens": cost_per_1k,
            "estimated_total": cost_per_1k * usage,
            "note": "Estimate from the router's relative cost model, not provider billing.",
        },
    }


@router.get("", response_model=list[ProviderSummary])
async def list_providers(
    settings: Settings = Depends(get_settings),
) -> list[ProviderSummary]:
    """Backward-compatible provider summary (M8 shape)."""
    return [
        ProviderSummary(
            id=provider_id,
            status="ready" if settings.is_provider_ready(provider_id) else "unconfigured",
            enabled=settings.is_provider_ready(provider_id),
        )
        for provider_id in KNOWN_PROVIDERS
    ]


@router.get("/runtime")
async def providers_runtime(
    settings: Settings = Depends(get_settings),
    pipeline=Depends(get_pipeline),
) -> dict[str, Any]:
    """M9.5: live runtime information for every known provider.

    Includes router-only providers (e.g. ollama) beyond the six
    settings-configurable ones, so usage recorded against them is
    visible rather than silently dropped.
    """
    return {
        provider_id: _provider_runtime(provider_id, pipeline, settings)
        for provider_id in _all_provider_ids(pipeline)
    }


@router.get("/{provider_id}")
async def get_provider(
    provider_id: str,
    settings: Settings = Depends(get_settings),
    pipeline=Depends(get_pipeline),
) -> dict[str, Any]:
    """One provider's full live runtime detail."""
    if provider_id not in _all_provider_ids(pipeline):
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"Unknown provider '{provider_id}'.",
                "code": "PROVIDER_NOT_FOUND",
            },
        )
    return {
        "id": provider_id,
        "status": "ready" if settings.is_provider_ready(provider_id) else "unconfigured",
        "enabled": settings.is_provider_ready(provider_id),
        **_provider_runtime(provider_id, pipeline, settings),
    }


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
