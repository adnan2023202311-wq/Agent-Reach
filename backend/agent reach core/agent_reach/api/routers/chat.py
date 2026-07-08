"""
API layer: /api/v1/chat endpoint.

Layer: Interface/Presentation.

M7.5: The chat endpoint uses the IntelligentPipeline when available,
which layers Router → Memory → Context → MOA → Planner → Agents →
Reflection → Knowledge Graph → Learning → Tutti around core execution.
Falls back to MainController when no pipeline is registered.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request

from api.dependencies import get_controller
from api.schemas import ChatRequest, ChatResponse
from core.controller import MainController

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    http_request: Request,
    controller: MainController = Depends(get_controller),
) -> ChatResponse:
    """Process a chat message through the intelligent pipeline.

    M7.5: Uses the IntelligentPipeline registered on app.state.
    Falls back to MainController for backward compatibility.
    """
    pipeline = getattr(http_request.app.state, "pipeline", None)

    if pipeline is not None:
        try:
            result = await pipeline.process(
                request.message,
                session_id=request.session_id,
                extra_context=request.context,
            )
            # M9.3: surface the trace so every chat is observable.
            return ChatResponse.from_outcome(
                result.outcome,
                session_id=request.session_id,
                request_id=result.trace.request_id,
                trace=result.trace.to_dict(),
            )
        except Exception:
            logger.exception("Pipeline failed, falling back to controller")

    outcome = await controller.handle_request(request.message)
    return ChatResponse.from_outcome(outcome, session_id=request.session_id)
