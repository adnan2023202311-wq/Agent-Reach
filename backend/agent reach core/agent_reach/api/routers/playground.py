"""
API layer: /api/v1/playground — Model Playground (M9.1).

Layer: Interface/Presentation.

M9.1 replaces the M8 stub (fabricated outputs, invented latency/cost/
quality) with the real PlaygroundComparator (playground/compare.py):
configured providers are called concurrently through the existing
ProviderManager client factories, latency is measured, unconfigured
providers are reported honestly, and cost/tokens are labeled
estimates derived from the router cost model.
"""

from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from config.settings import Settings, get_settings
from playground.compare import PlaygroundComparator

router = APIRouter(prefix="/api/v1/playground", tags=["playground"])


class CompareRequest(BaseModel):
    prompt: str = Field(min_length=1)
    providers: List[str] = Field(min_length=1)
    max_tokens: int = Field(default=512, ge=1, le=8192)
    system: str = ""


@router.post("/compare")
async def compare_models(
    req: CompareRequest, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Run one prompt against several providers — real calls only."""
    comparator = PlaygroundComparator(settings)
    try:
        return await comparator.compare(
            req.prompt,
            req.providers,
            max_tokens=req.max_tokens,
            system=req.system,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "code": "INVALID_COMPARE_REQUEST"},
        ) from exc


@router.get("/models")
async def playground_models(
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Real provider/model availability from configuration."""
    return PlaygroundComparator(settings).list_models()
