"""
API layer: /api/v1/improvement — Continuous Self-Improvement Loop (M9.27).

Layer: Interface/Presentation.

Exposes the SelfImprovementLoop: cadence status, manual cycle
trigger, and the full record of past cycles (what each cycle actually
did — optimization report, prompt proposals, knowledge/learning
snapshots, per-stage errors).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/v1/improvement", tags=["improvement"])


def _loop(request: Request):
    loop = getattr(request.app.state, "improvement_loop", None)
    if loop is None:
        raise HTTPException(status_code=503, detail="Improvement loop not available")
    return loop


@router.get("/status")
async def improvement_status(request: Request) -> dict[str, Any]:
    """Cadence and last-cycle summary."""
    return _loop(request).get_status()


@router.post("/cycle")
async def trigger_cycle(request: Request) -> dict[str, Any]:
    """Run one improvement cycle immediately."""
    cycle = await _loop(request).run_cycle(trigger_request_id="manual")
    return cycle.to_dict()


@router.get("/cycles")
async def list_cycles(request: Request, limit: int = 20) -> dict[str, Any]:
    """Past improvement cycles, newest first."""
    cycles = _loop(request).get_cycles(limit=limit)
    return {"cycles": [c.to_dict() for c in cycles], "count": len(cycles)}
