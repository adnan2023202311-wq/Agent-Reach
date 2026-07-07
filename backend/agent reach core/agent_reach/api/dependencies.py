"""
API layer: FastAPI dependency providers.

Layer: Interface/Presentation.

This file was deliberately removed during Milestone 2 — at the time,
get_controller() had exactly one caller (api/routers/chat.py), and a
whole file for a one-line function was overhead (see
docs/ARCHITECTURE.md, "Files that were removed for being wrappers").
It's back now because that condition changed: agents.py, tools.py, and
dashboard.py all need the same controller. This is the file-count
trade-off resolving itself in the direction the original note
predicted, not a reversal of the decision.

Milestone 6 additions: conversation engine, session manager, workflow
engine, and workflow registry are now also app.state singletons that
routers need access to.
"""

from __future__ import annotations

from fastapi import Request

from core.controller import MainController


def get_controller(request: Request) -> MainController:
    return request.app.state.controller


def get_conversation_engine(request: Request):
    """Return the ConversationEngine built in the composition root."""
    return getattr(request.app.state, "conversation_engine", None)


def get_session_manager(request: Request):
    """Return the SessionManager built in the composition root."""
    return getattr(request.app.state, "session_manager", None)


def get_workflow_engine(request: Request):
    """Return the WorkflowEngine built in the composition root."""
    return getattr(request.app.state, "workflow_engine", None)


def get_workflow_registry(request: Request):
    """Return the WorkflowRegistry built in the composition root."""
    return getattr(request.app.state, "workflow_registry", None)

def get_pipeline(request: Request):
    """Return the IntelligentPipeline built in the composition root (M7.5)."""
    return getattr(request.app.state, "pipeline", None)
