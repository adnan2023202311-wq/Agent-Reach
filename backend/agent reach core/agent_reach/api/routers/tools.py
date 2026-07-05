"""
API layer: /api/v1/tools.

Layer: Interface/Presentation.

Returns an honestly empty list. infrastructure/tool_manager.py exists,
but nothing in composition.py constructs a ToolManager or registers
any tool with it (see docs/ARCHITECTURE.md, "Remaining weaknesses") —
wiring one up here just to call an always-empty `.list()` would be
machinery for zero behavioral gain. This reports the true state
directly instead.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


@router.get("", response_model=list[dict])
async def list_tools() -> list[dict]:
    return []


@router.patch("/{tool_id}")
async def update_tool(tool_id: str) -> None:
    """Not implemented — see api/routers/agents.py's update_agent for
    the identical reasoning (no persistence layer, not called by the
    current frontend)."""
    raise HTTPException(
        status_code=501,
        detail={
            "message": "Editing tool configuration isn't supported yet.",
            "code": "NOT_IMPLEMENTED",
        },
    )
