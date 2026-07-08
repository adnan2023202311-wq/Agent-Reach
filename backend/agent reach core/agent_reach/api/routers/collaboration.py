"""
API layer: /api/v1/collaboration — Enterprise Intelligence (M9.23).

Layer: Interface/Presentation.

M9.23 replaces the M8 mock (three hardcoded teams, two fake audit
entries, create_team that persisted nothing) with the real
EnterpriseEngine: organizations, members, roles/permissions
(enforced RBAC), teams, workspaces (with session scopes namespacing
shared memory/knowledge inside the shared engines), real audit log,
and real analytics.

Actor identity comes from the X-Member-Id header. Full authentication
(tokens/SSO) builds on the existing auth/ layer in a later block; the
RBAC layer beneath is already real and enforced.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from enterprise import (
    EnterpriseEngine,
    NotFound,
    Permission,
    PermissionDenied,
    Role,
)

router = APIRouter(prefix="/api/v1/collaboration", tags=["collaboration"])


class BootstrapRequest(BaseModel):
    organization_name: str = Field(min_length=1)
    owner_email: str = Field(min_length=3)
    owner_name: str = ""


class MemberCreate(BaseModel):
    email: str = Field(min_length=3)
    display_name: str = ""
    role: str = "member"


class RoleChange(BaseModel):
    role: str


class TeamCreate(BaseModel):
    name: str = Field(min_length=1)


class TeamMemberOp(BaseModel):
    member_id: str = Field(min_length=1)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1)
    team_id: str = ""


def _engine(request: Request) -> EnterpriseEngine:
    engine = getattr(request.app.state, "enterprise", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Enterprise engine not available")
    return engine


def _actor(x_member_id: Optional[str]) -> str:
    if not x_member_id:
        raise HTTPException(
            status_code=401,
            detail={
                "message": "X-Member-Id header is required for this operation.",
                "code": "MISSING_ACTOR",
            },
        )
    return x_member_id


def _parse_role(value: str) -> Role:
    try:
        return Role(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"Unknown role '{value}'. Valid: {[r.value for r in Role]}",
                "code": "INVALID_ROLE",
            },
        ) from exc


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionDenied):
        return HTTPException(
            status_code=403, detail={"message": str(exc), "code": "PERMISSION_DENIED"}
        )
    if isinstance(exc, NotFound):
        return HTTPException(
            status_code=404, detail={"message": str(exc.args[0]), "code": "NOT_FOUND"}
        )
    if isinstance(exc, ValueError):
        return HTTPException(
            status_code=422, detail={"message": str(exc), "code": "INVALID_INPUT"}
        )
    raise exc


# ── Bootstrap & organizations ───────────────────────────────────


@router.post("/bootstrap")
async def bootstrap(body: BootstrapRequest, request: Request) -> dict[str, Any]:
    """Create an organization with its first owner (unauthenticated
    by design — everything else requires an actor)."""
    try:
        org, owner = _engine(request).bootstrap_organization(
            body.organization_name, body.owner_email, body.owner_name
        )
    except ValueError as exc:
        raise _translate(exc) from exc
    return {"organization": org.to_dict(), "owner": owner.to_dict()}


@router.get("/organizations")
async def list_orgs(request: Request) -> dict[str, Any]:
    orgs = _engine(request).list_organizations()
    return {"items": [o.to_dict() for o in orgs], "count": len(orgs)}


@router.get("/organizations/{organization_id}/analytics")
async def org_analytics(organization_id: str, request: Request) -> dict[str, Any]:
    try:
        return _engine(request).get_analytics(organization_id)
    except NotFound as exc:
        raise _translate(exc) from exc


# ── Members ─────────────────────────────────────────────────────


@router.get("/organizations/{organization_id}/members")
async def list_members(organization_id: str, request: Request) -> dict[str, Any]:
    members = _engine(request).list_members(organization_id)
    return {"items": [m.to_dict() for m in members], "count": len(members)}


@router.post("/members")
async def add_member(
    body: MemberCreate,
    request: Request,
    x_member_id: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    engine = _engine(request)
    try:
        member = engine.add_member(
            _actor(x_member_id),
            body.email,
            display_name=body.display_name,
            role=_parse_role(body.role),
        )
    except (PermissionDenied, NotFound, ValueError) as exc:
        raise _translate(exc) from exc
    return member.to_dict()


@router.patch("/members/{member_id}/role")
async def change_role(
    member_id: str,
    body: RoleChange,
    request: Request,
    x_member_id: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    engine = _engine(request)
    try:
        member = engine.change_role(
            _actor(x_member_id), member_id, _parse_role(body.role)
        )
    except (PermissionDenied, NotFound, ValueError) as exc:
        raise _translate(exc) from exc
    return member.to_dict()


@router.get("/members/{member_id}/permissions")
async def member_permissions(member_id: str, request: Request) -> dict[str, Any]:
    try:
        permissions = _engine(request).get_permissions(member_id)
    except NotFound as exc:
        raise _translate(exc) from exc
    return {"member_id": member_id, "permissions": permissions}


# ── Teams ───────────────────────────────────────────────────────


@router.get("/teams")
async def list_teams(
    request: Request, organization_id: str = ""
) -> dict[str, Any]:
    engine = _engine(request)
    if organization_id:
        teams = engine.list_teams(organization_id)
    else:
        teams = [
            t for org in engine.list_organizations()
            for t in engine.list_teams(org.organization_id)
        ]
    return {"items": [t.to_dict() for t in teams], "count": len(teams)}


@router.post("/teams")
async def create_team(
    body: TeamCreate,
    request: Request,
    x_member_id: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        team = _engine(request).create_team(_actor(x_member_id), body.name)
    except (PermissionDenied, NotFound, ValueError) as exc:
        raise _translate(exc) from exc
    return team.to_dict()


@router.post("/teams/{team_id}/members")
async def add_team_member(
    team_id: str,
    body: TeamMemberOp,
    request: Request,
    x_member_id: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        team = _engine(request).add_to_team(
            _actor(x_member_id), team_id, body.member_id
        )
    except (PermissionDenied, NotFound) as exc:
        raise _translate(exc) from exc
    return team.to_dict()


@router.delete("/teams/{team_id}/members/{member_id}")
async def remove_team_member(
    team_id: str,
    member_id: str,
    request: Request,
    x_member_id: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        team = _engine(request).remove_from_team(
            _actor(x_member_id), team_id, member_id
        )
    except (PermissionDenied, NotFound) as exc:
        raise _translate(exc) from exc
    return team.to_dict()


# ── Workspaces ──────────────────────────────────────────────────


@router.get("/workspaces")
async def list_workspaces(
    request: Request, organization_id: str = "", team_id: str = ""
) -> dict[str, Any]:
    engine = _engine(request)
    if organization_id:
        workspaces = engine.list_workspaces(organization_id, team_id=team_id)
    else:
        workspaces = [
            w for org in engine.list_organizations()
            for w in engine.list_workspaces(org.organization_id, team_id=team_id)
        ]
    return {"items": [w.to_dict() for w in workspaces], "count": len(workspaces)}


@router.post("/workspaces")
async def create_workspace(
    body: WorkspaceCreate,
    request: Request,
    x_member_id: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        workspace = _engine(request).create_workspace(
            _actor(x_member_id), body.name, team_id=body.team_id
        )
    except (PermissionDenied, NotFound, ValueError) as exc:
        raise _translate(exc) from exc
    return workspace.to_dict()


# ── Audit ───────────────────────────────────────────────────────


@router.get("/audit")
async def audit_log(
    request: Request,
    actor_id: str = "",
    action_prefix: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    """Real audit entries, newest first — only ever appended by real
    operations."""
    entries = _engine(request).get_audit_log(
        actor_id=actor_id, action_prefix=action_prefix, limit=limit
    )
    return {"items": [e.to_dict() for e in entries], "count": len(entries)}
