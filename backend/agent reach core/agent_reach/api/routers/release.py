"""
API layer: /api/v1/release — Autonomous Release Pipeline (M9.25/M9.30).

Layer: Interface/Presentation.

Exposes the ReleasePipeline: full validation runs, gated publication
(refused unless every validation passes — the refusal is a real
release record with the failing checks), and release history.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/release", tags=["release"])


class PublishRequest(BaseModel):
    bump: str = "minor"
    notes: str = ""


def _pipeline(request: Request):
    release = getattr(request.app.state, "release_pipeline", None)
    if release is None:
        raise HTTPException(status_code=503, detail="Release pipeline not available")
    return release


@router.post("/validate")
async def validate_release(request: Request) -> dict[str, Any]:
    """Run every release validation without publishing."""
    checks = await _pipeline(request).validate_all()
    return {
        "checks": checks,
        "passed": all(c["passed"] for c in checks),
    }


@router.post("/publish")
async def publish_release(body: PublishRequest, request: Request) -> dict[str, Any]:
    """Validate everything; publish ONLY when all validations pass."""
    try:
        record = await _pipeline(request).publish(bump=body.bump, notes=body.notes)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "code": "INVALID_PUBLISH"},
        ) from exc
    return record.to_dict()


@router.get("/releases")
async def list_releases(request: Request, limit: int = 20) -> dict[str, Any]:
    releases = _pipeline(request).list_releases(limit=limit)
    return {"releases": [r.to_dict() for r in releases], "count": len(releases)}


@router.get("/releases/{release_id}")
async def get_release(release_id: str, request: Request) -> dict[str, Any]:
    record = _pipeline(request).get_release(release_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Release '{release_id}' not found.", "code": "RELEASE_NOT_FOUND"},
        )
    return record.to_dict()
