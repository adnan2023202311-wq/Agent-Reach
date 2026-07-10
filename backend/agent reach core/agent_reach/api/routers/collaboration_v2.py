"""
API layer: /api/v1/collaboration/v2 — AI Collaboration Platform (M10.18).

Shared projects, shared workspaces, shared memory, shared reasoning,
and live collaboration. Multiple users and agents work together in
real-time on shared artifacts.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/collaboration/v2", tags=["ai-collaboration"])


class SharedProject(BaseModel):
    project_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    owner_id: str = ""
    members: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    shared_memory: bool = True
    shared_reasoning: bool = True
    created_at: float = Field(default_factory=time.time)


class CollaborationSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    participants: list[str] = Field(default_factory=list)  # user_ids + agent_ids
    status: str = "active"  # active | paused | ended
    started_at: float = Field(default_factory=time.time)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)


_projects: dict[str, SharedProject] = {}
_sessions: dict[str, CollaborationSession] = {}
_live_events: dict[str, list[dict[str, Any]]] = {}  # session_id → events


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""
    owner_id: str = ""
    members: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)


@router.post("/projects")
async def create_project(request: CreateProjectRequest) -> dict[str, Any]:
    """Create a shared project."""
    project = SharedProject(
        name=request.name, description=request.description, owner_id=request.owner_id,
        members=request.members, agents=request.agents,
    )
    _projects[project.project_id] = project
    return {"project_id": project.project_id, "name": project.name, "status": "created"}


@router.get("/projects")
async def list_projects(user_id: Optional[str] = None) -> dict[str, Any]:
    """List shared projects, optionally filtered by user membership."""
    projects = list(_projects.values())
    if user_id:
        projects = [p for p in projects if user_id in p.members or user_id == p.owner_id]
    return {"projects": [p.model_dump() for p in projects], "count": len(projects)}


@router.get("/projects/{project_id}")
async def get_project(project_id: str) -> dict[str, Any]:
    project = _projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.model_dump()


@router.post("/projects/{project_id}/members")
async def add_member(project_id: str, user_id: str) -> dict[str, Any]:
    """Add a member to a shared project."""
    project = _projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if user_id not in project.members:
        project.members.append(user_id)
    return {"project_id": project_id, "members": project.members}


class StartSessionRequest(BaseModel):
    project_id: str
    participants: list[str] = Field(default_factory=list)


@router.post("/sessions")
async def start_session(request: StartSessionRequest) -> dict[str, Any]:
    """Start a live collaboration session."""
    session = CollaborationSession(
        project_id=request.project_id, participants=request.participants,
    )
    _sessions[session.session_id] = session
    _live_events[session.session_id] = []
    return {"session_id": session.session_id, "status": "active", "participants": session.participants}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.model_dump()


@router.post("/sessions/{session_id}/events")
async def post_event(session_id: str, participant_id: str, event_type: str, content: str) -> dict[str, Any]:
    """Post a live event to a collaboration session."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    event = {
        "event_id": str(uuid.uuid4()),
        "participant_id": participant_id,
        "event_type": event_type,  # message | edit | cursor | thought | decision
        "content": content,
        "timestamp": time.time(),
    }
    _live_events.setdefault(session_id, []).append(event)
    return {"event_id": event["event_id"], "status": "posted"}


@router.get("/sessions/{session_id}/events")
async def get_events(session_id: str, since: float = 0.0) -> dict[str, Any]:
    """Get live events from a collaboration session."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    events = [e for e in _live_events.get(session_id, []) if e["timestamp"] > since]
    return {"events": events, "count": len(events)}


@router.post("/sessions/{session_id}/end")
async def end_session(session_id: str) -> dict[str, Any]:
    """End a collaboration session."""
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    session.status = "ended"
    return {"session_id": session_id, "status": "ended"}
