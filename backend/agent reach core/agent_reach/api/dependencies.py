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
"""

from __future__ import annotations

from fastapi import Request

from core.controller import MainController


def get_controller(request: Request) -> MainController:
    return request.app.state.controller
