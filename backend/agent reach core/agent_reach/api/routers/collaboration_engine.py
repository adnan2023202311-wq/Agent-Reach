"""
API layer: /api/v1/agents/collaborate — Multi-Agent Collaboration (M9.29).

Layer: Interface/Presentation.

Exposes the CollaborationEngine: decomposition into dependency waves,
parallel dispatch, shared-reasoning messages, consensus/conflict
records. Distinct from /api/v1/collaboration (M9.23 enterprise
teams) — this is agent-runtime collaboration.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/agents/collaborate", tags=["agent-collaboration"])


class CollaborateRequest(BaseModel):
    request: str = Field(min_length=1)


def _engine(request: Request):
    engine = getattr(request.app.state, "collaboration_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Collaboration engine not available")
    return engine


@router.post("")
async def collaborate(body: CollaborateRequest, request: Request) -> dict[str, Any]:
    """Run one request through multi-agent collaboration."""
    try:
        record = await _engine(request).collaborate(body.request)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "code": "INVALID_COLLABORATION"},
        ) from exc
    return record.to_dict()


@router.get("/records")
async def list_records(request: Request, limit: int = 20) -> dict[str, Any]:
    """Past collaborations, newest first."""
    records = _engine(request).list_records(limit=limit)
    return {"records": [r.to_dict() for r in records], "count": len(records)}


@router.get("/records/{collaboration_id}")
async def get_record(collaboration_id: str, request: Request) -> dict[str, Any]:
    record = _engine(request).get_record(collaboration_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"Collaboration '{collaboration_id}' not found.",
                "code": "COLLABORATION_NOT_FOUND",
            },
        )
    return record.to_dict()


@router.get("/records/{collaboration_id}/reasoning")
async def shared_reasoning(collaboration_id: str, request: Request) -> dict[str, Any]:
    """The real shared-context messages exchanged during one run."""
    engine = _engine(request)
    if engine.get_record(collaboration_id) is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"Collaboration '{collaboration_id}' not found.",
                "code": "COLLABORATION_NOT_FOUND",
            },
        )
    messages = engine.get_shared_reasoning(collaboration_id)
    return {"messages": messages, "count": len(messages)}
