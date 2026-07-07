"""
API layer: /api/v1/conversations — conversation execution and history.

Layer: Interface/Presentation.

Provides endpoints for:
- creating a conversation session
- sending a message (conversation turn)
- retrieving conversation history
- listing sessions
- terminating a session

Reuses the ConversationEngine and SessionManager built in the
composition root.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_conversation_engine, get_session_manager

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    user_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateSessionResponse(BaseModel):
    session_id: str
    state: str
    created_at: float


class SendMessageRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


class SendMessageResponse(BaseModel):
    session_id: str
    message_id: str
    role: str
    content: str
    plan_id: str
    status: str


class MessageResponse(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str
    timestamp: float
    metadata: dict[str, Any]


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    state: str
    created_at: float
    updated_at: float
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    session_manager=Depends(get_session_manager),
) -> CreateSessionResponse:
    """Create a new conversation session."""
    session = session_manager.create_session(
        user_id=request.user_id,
        metadata=request.metadata,
    )
    return CreateSessionResponse(
        session_id=session.session_id,
        state=session.state.value,
        created_at=session.created_at,
    )


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    user_id: str = "",
    session_manager=Depends(get_session_manager),
) -> list[SessionResponse]:
    """List conversation sessions, optionally filtered by user_id."""
    sessions = session_manager.list_sessions(user_id=user_id)
    return [
        SessionResponse(
            session_id=s.session_id,
            user_id=s.user_id,
            state=s.state.value,
            created_at=s.created_at,
            updated_at=s.updated_at,
            metadata=s.metadata,
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    session_manager=Depends(get_session_manager),
) -> SessionResponse:
    """Return a single session by ID."""
    session = session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        state=session.state.value,
        created_at=session.created_at,
        updated_at=session.updated_at,
        metadata=session.metadata,
    )


@router.post("/sessions/{session_id}/messages", response_model=SendMessageResponse)
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    engine=Depends(get_conversation_engine),
) -> SendMessageResponse:
    """Send a message in a conversation session (one turn)."""
    try:
        result = await engine.send_message(
            session_id,
            request.message,
            extra_context=request.context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SendMessageResponse(
        session_id=result.session.session_id,
        message_id=result.assistant_message.message_id,
        role=result.assistant_message.role.value,
        content=result.assistant_message.content,
        plan_id=result.outcome.plan.id if result.outcome else "",
        status=result.outcome.status.value if result.outcome else "unknown",
    )


@router.get("/sessions/{session_id}/history", response_model=list[MessageResponse])
async def get_history(
    session_id: str,
    engine=Depends(get_conversation_engine),
) -> list[MessageResponse]:
    """Return the full conversation history for a session."""
    history = engine.get_history(session_id)
    return [
        MessageResponse(
            message_id=m.message_id,
            session_id=m.session_id,
            role=m.role.value,
            content=m.content,
            timestamp=m.timestamp,
            metadata=m.metadata,
        )
        for m in history
    ]


@router.post("/sessions/{session_id}/terminate")
async def terminate_session(
    session_id: str,
    session_manager=Depends(get_session_manager),
) -> dict[str, str]:
    """Terminate a conversation session."""
    if not session_manager.terminate_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "terminated", "session_id": session_id}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    session_manager=Depends(get_session_manager),
    engine=Depends(get_conversation_engine),
) -> dict[str, str]:
    """Delete a conversation session and its history."""
    engine.clear_history(session_id)
    engine.clear_context(session_id)
    if not session_manager.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}
