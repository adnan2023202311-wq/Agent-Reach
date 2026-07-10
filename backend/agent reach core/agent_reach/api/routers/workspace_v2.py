"""
API layer: /api/v1/workspace/v2 — Workspace Intelligence (M10.30).

Cross-session context + project state. The workspace tracks the
user's current project, active files, recent conversations, and
relevant context — enabling the platform to understand what the user
is working on across sessions.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/workspace/v2", tags=["workspace-intelligence"])


class Workspace(BaseModel):
    workspace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    owner_id: str = ""
    description: str = ""
    active_project: str = ""
    open_files: list[str] = Field(default_factory=list)
    pinned_context: list[dict[str, Any]] = Field(default_factory=list)  # manually pinned items
    auto_context: list[dict[str, Any]] = Field(default_factory=list)  # automatically gathered
    session_history: list[str] = Field(default_factory=list)  # conversation session_ids
    created_at: float = Field(default_factory=time.time)
    last_active: float = Field(default_factory=time.time)


class ProjectState(BaseModel):
    project_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str
    name: str
    path: str = ""
    branch: str = "main"
    status: str = "active"  # active | paused | archived
    milestones: list[dict[str, Any]] = Field(default_factory=list)
    open_tasks: list[dict[str, Any]] = Field(default_factory=list)
    recent_changes: list[dict[str, Any]] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)


_workspaces: dict[str, Workspace] = {}
_projects: dict[str, ProjectState] = {}


class CreateWorkspaceRequest(BaseModel):
    name: str
    owner_id: str = ""
    description: str = ""


@router.post("/workspaces")
async def create_workspace(request: CreateWorkspaceRequest) -> dict[str, Any]:
    """Create a new workspace."""
    ws = Workspace(name=request.name, owner_id=request.owner_id, description=request.description)
    _workspaces[ws.workspace_id] = ws
    return {"workspace_id": ws.workspace_id, "name": ws.name, "status": "created"}


@router.get("/workspaces")
async def list_workspaces(owner_id: Optional[str] = None) -> dict[str, Any]:
    workspaces = list(_workspaces.values())
    if owner_id:
        workspaces = [w for w in workspaces if w.owner_id == owner_id]
    return {"workspaces": [w.model_dump() for w in workspaces], "count": len(workspaces)}


@router.get("/workspaces/{workspace_id}")
async def get_workspace(workspace_id: str) -> dict[str, Any]:
    ws = _workspaces.get(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    ws.last_active = time.time()
    return ws.model_dump()


class UpdateContextRequest(BaseModel):
    open_files: Optional[list[str]] = None
    pinned_context: Optional[list[dict[str, Any]]] = None
    auto_context: Optional[list[dict[str, Any]]] = None


@router.put("/workspaces/{workspace_id}/context")
async def update_context(workspace_id: str, request: UpdateContextRequest) -> dict[str, Any]:
    """Update the workspace's context (open files, pinned items, auto-gathered context)."""
    ws = _workspaces.get(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if request.open_files is not None:
        ws.open_files = request.open_files
    if request.pinned_context is not None:
        ws.pinned_context = request.pinned_context
    if request.auto_context is not None:
        ws.auto_context = request.auto_context
    ws.last_active = time.time()
    return {"workspace_id": workspace_id, "status": "updated", "context_items": len(ws.pinned_context) + len(ws.auto_context)}


@router.post("/workspaces/{workspace_id}/sessions/{session_id}")
async def link_session(workspace_id: str, session_id: str) -> dict[str, Any]:
    """Link a conversation session to the workspace."""
    ws = _workspaces.get(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if session_id not in ws.session_history:
        ws.session_history.append(session_id)
    return {"workspace_id": workspace_id, "session_id": session_id, "status": "linked"}


@router.get("/workspaces/{workspace_id}/context")
async def get_context(workspace_id: str) -> dict[str, Any]:
    """Get the full context for a workspace (pinned + auto + session history)."""
    ws = _workspaces.get(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {
        "workspace_id": workspace_id,
        "open_files": ws.open_files,
        "pinned_context": ws.pinned_context,
        "auto_context": ws.auto_context,
        "session_count": len(ws.session_history),
        "recent_sessions": ws.session_history[-5:],
        "active_project": ws.active_project,
    }


class CreateProjectRequest(BaseModel):
    workspace_id: str
    name: str
    path: str = ""


@router.post("/projects")
async def create_project(request: CreateProjectRequest) -> dict[str, Any]:
    """Create a project within a workspace."""
    if request.workspace_id not in _workspaces:
        raise HTTPException(status_code=404, detail="Workspace not found")
    project = ProjectState(workspace_id=request.workspace_id, name=request.name, path=request.path)
    _projects[project.project_id] = project
    _workspaces[request.workspace_id].active_project = project.project_id
    return {"project_id": project.project_id, "name": project.name, "status": "created"}


@router.get("/projects")
async def list_projects(workspace_id: Optional[str] = None) -> dict[str, Any]:
    projects = list(_projects.values())
    if workspace_id:
        projects = [p for p in projects if p.workspace_id == workspace_id]
    return {"projects": [p.model_dump() for p in projects], "count": len(projects)}


class AddTaskRequest(BaseModel):
    title: str
    description: str = ""
    priority: int = 5


@router.post("/projects/{project_id}/tasks")
async def add_task(project_id: str, request: AddTaskRequest) -> dict[str, Any]:
    """Add a task to a project."""
    project = _projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    task = {"task_id": str(uuid.uuid4()), "title": request.title, "description": request.description,
            "priority": request.priority, "status": "open", "created_at": time.time()}
    project.open_tasks.append(task)
    return {"task_id": task["task_id"], "status": "added"}


@router.post("/projects/{project_id}/tasks/{task_id}/complete")
async def complete_task(project_id: str, task_id: str) -> dict[str, Any]:
    """Mark a project task as completed."""
    project = _projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    for task in project.open_tasks:
        if task["task_id"] == task_id:
            task["status"] = "completed"
            task["completed_at"] = time.time()
            return {"task_id": task_id, "status": "completed"}
    raise HTTPException(status_code=404, detail="Task not found")


@router.get("/stats")
async def workspace_stats() -> dict[str, Any]:
    return {
        "total_workspaces": len(_workspaces),
        "total_projects": len(_projects),
        "total_tasks": sum(len(p.open_tasks) for p in _projects.values()),
        "open_tasks": sum(1 for p in _projects.values() for t in p.open_tasks if t["status"] == "open"),
    }
