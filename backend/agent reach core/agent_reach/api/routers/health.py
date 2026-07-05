"""API layer: health check endpoint, for uptime monitors and orchestrators."""

from __future__ import annotations

from fastapi import APIRouter

from config.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}
