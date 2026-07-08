"""
API layer: /api/v1/organization — AI Engineering Organization (M9.12).

Layer: Interface/Presentation.

Exposes the EngineeringOrganization: the org chart (roles,
dependencies, execution waves), project runs (every role a real
pipeline execution with a persisted trace), and the inter-role
communication audit trail.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/organization", tags=["organization"])


class ProjectRequest(BaseModel):
    objective: str = Field(min_length=1)


def _organization(request: Request):
    organization = getattr(request.app.state, "engineering_organization", None)
    if organization is None:
        raise HTTPException(status_code=503, detail="Engineering organization not available")
    return organization


@router.get("/chart")
async def organization_chart(request: Request) -> dict[str, Any]:
    """Roles, charters, dependencies, and execution waves."""
    return _organization(request).describe()


@router.post("/projects")
async def run_project(body: ProjectRequest, request: Request) -> dict[str, Any]:
    """Run one objective through the full organization."""
    try:
        record = await _organization(request).run_project(body.objective)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "code": "INVALID_PROJECT"},
        ) from exc
    return record.to_dict()


@router.get("/projects")
async def list_projects(request: Request, limit: int = 20) -> dict[str, Any]:
    projects = _organization(request).list_projects(limit=limit)
    return {"projects": [p.to_dict() for p in projects], "count": len(projects)}


@router.get("/projects/{project_id}")
async def get_project(project_id: str, request: Request) -> dict[str, Any]:
    record = _organization(request).get_project(project_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Project '{project_id}' not found.", "code": "PROJECT_NOT_FOUND"},
        )
    return record.to_dict()


@router.get("/projects/{project_id}/communications")
async def project_communications(project_id: str, request: Request) -> dict[str, Any]:
    """Real inter-role messages exchanged during one project."""
    organization = _organization(request)
    if organization.get_project(project_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Project '{project_id}' not found.", "code": "PROJECT_NOT_FOUND"},
        )
    messages = organization.get_communications(project_id)
    return {"messages": messages, "count": len(messages)}
