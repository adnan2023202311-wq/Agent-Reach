"""
API layer: /api/v1/optimization — Self Optimization Engine (M9.14).

Layer: Interface/Presentation.

Exposes the SelfOptimizationEngine: analysis of real runtime data
(latency, errors, providers, memory, routing, context) and controlled
application of SAFE maintenance operations with real before/after
measurements. Advisory findings are never auto-applied.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/optimization", tags=["optimization"])


class ApplyRequest(BaseModel):
    action_ids: Optional[list[str]] = Field(
        default=None,
        description="Apply only these actions (must be safe). None = all safe actions.",
    )


def _engine(request: Request):
    engine = getattr(request.app.state, "optimization_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Optimization engine not available")
    return engine


@router.get("/analyze")
async def analyze(request: Request) -> dict[str, Any]:
    """Analyze real runtime data. Empty runtime → honest empty result."""
    actions = _engine(request).analyze()
    return {
        "actions": [a.to_dict() for a in actions],
        "count": len(actions),
        "safe_count": sum(1 for a in actions if a.safe),
        "advisory_count": sum(1 for a in actions if not a.safe),
    }


@router.post("/apply")
async def apply_optimizations(body: ApplyRequest, request: Request) -> dict[str, Any]:
    """Apply safe optimization actions and report real measurements."""
    engine = _engine(request)
    actions = engine.analyze()
    if body.action_ids is not None:
        wanted = set(body.action_ids)
        selected = [a for a in actions if a.action_id in wanted]
        missing = wanted - {a.action_id for a in selected}
        if missing:
            raise HTTPException(
                status_code=404,
                detail={
                    "message": f"Unknown action ids: {sorted(missing)}. "
                    "Actions are ephemeral — re-run /analyze and use fresh ids.",
                    "code": "ACTION_NOT_FOUND",
                },
            )
        unsafe = [a.action_id for a in selected if not a.safe]
        if unsafe:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"Actions {unsafe} are advisory and cannot be auto-applied.",
                    "code": "UNSAFE_ACTION",
                },
            )
        return engine.apply(selected)
    return engine.apply(actions)


@router.get("/reports")
async def optimization_reports(request: Request, limit: int = 20) -> dict[str, Any]:
    """Past optimization reports, newest first."""
    reports = _engine(request).get_reports(limit=limit)
    return {"reports": reports, "count": len(reports)}
