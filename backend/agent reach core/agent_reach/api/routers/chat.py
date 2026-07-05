"""
API layer: /api/v1/chat endpoint.

Layer: Interface/Presentation.

get_controller() moved back to api/dependencies.py — see that file's
docstring for why.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_controller
from api.schemas import ChatRequest, ChatResponse
from core.controller import MainController

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    controller: MainController = Depends(get_controller),
) -> ChatResponse:
    outcome = await controller.handle_request(request.message)
    return ChatResponse.from_outcome(outcome, session_id=request.session_id)
