"""
API layer: /api/v1/events — Runtime Event Stream (M9.24).

Layer: Interface/Presentation.

Serves the RuntimeEventHub's recorded event log: every event is a
real record of something that flowed through the runtime (pipeline
stages, tool executions, workflow lifecycle). Nothing synthetic.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/v1/events", tags=["events"])


def _hub(request: Request):
    hub = getattr(request.app.state, "event_hub", None)
    if hub is None:
        raise HTTPException(status_code=503, detail="Event hub not available")
    return hub


@router.get("")
async def list_events(
    request: Request,
    event_type: str = "",
    limit: int = 100,
    since: float = 0.0,
) -> dict[str, Any]:
    """Recent runtime events, newest first.

    ``since`` (epoch seconds) supports incremental polling.
    """
    hub = _hub(request)
    events = hub.get_events(event_type=event_type, limit=limit, since=since)
    return {"events": [e.to_dict() for e in events], "count": len(events)}


@router.get("/stats")
async def event_stats(request: Request) -> dict[str, Any]:
    """Counts per event type from real traffic."""
    return _hub(request).get_stats()


@router.get("/types")
async def event_types(request: Request) -> dict[str, Any]:
    """The canonical runtime event vocabulary (M9.24)."""
    from core.runtime_events import RuntimeEvent

    return {"types": RuntimeEvent.all()}
