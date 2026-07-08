"""
Enterprise Intelligence Platform (M9.23).

Layer: Application/Core.

Real organizational state — organizations, teams, workspaces,
members, roles, permissions, and an audit log — replacing the M8
mock router that served three hardcoded teams and two fake audit
entries.

Design
------
- In-memory store consistent with the platform's other engines
  (SessionManager, WorkflowRegistry): one EnterpriseEngine instance
  lives on app.state; persistence backends are a composition concern
  (Settings.memory_backend) shared with the rest of the platform.
- RBAC is enforced, not decorative: every mutating operation takes
  an ``actor`` member id whose role must grant the permission, and
  every check/denial is a real code path (PermissionDenied).
- The audit log records every mutation with actor, action, resource,
  and timestamp — entries are only ever appended by real operations.
- Workspaces carry shared-resource references (memory/knowledge/
  workflow scopes) so shared state is namespaced per workspace
  rather than duplicated: the single LongCat/KG instances remain the
  storage; workspaces scope access via session prefixes.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Role(str, Enum):
    """Member roles, ordered by privilege."""

    VIEWER = "viewer"
    MEMBER = "member"
    ADMIN = "admin"
    OWNER = "owner"


class Permission(str, Enum):
    """Discrete permissions checked by the engine."""

    READ = "read"
    EXECUTE = "execute"
    MANAGE_TEAMS = "manage_teams"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_WORKSPACES = "manage_workspaces"
    MANAGE_ORGANIZATION = "manage_organization"


# Role → granted permissions. OWNER ⊃ ADMIN ⊃ MEMBER ⊃ VIEWER.
_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({Permission.READ}),
    Role.MEMBER: frozenset({Permission.READ, Permission.EXECUTE}),
    Role.ADMIN: frozenset(
        {
            Permission.READ,
            Permission.EXECUTE,
            Permission.MANAGE_TEAMS,
            Permission.MANAGE_MEMBERS,
            Permission.MANAGE_WORKSPACES,
        }
    ),
    Role.OWNER: frozenset(Permission),
}


class PermissionDenied(Exception):
    """The actor's role does not grant the required permission."""


class NotFound(KeyError):
    """A referenced enterprise entity does not exist."""


@dataclass
class Member:
    member_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    email: str = ""
    display_name: str = ""
    role: Role = Role.MEMBER
    organization_id: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "email": self.email,
            "display_name": self.display_name,
            "role": self.role.value,
            "organization_id": self.organization_id,
            "created_at": self.created_at,
        }


@dataclass
class Team:
    team_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    organization_id: str = ""
    member_ids: set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "name": self.name,
            "organization_id": self.organization_id,
            "member_ids": sorted(self.member_ids),
            "member_count": len(self.member_ids),
            "created_at": self.created_at,
        }


@dataclass
class Workspace:
    workspace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    organization_id: str = ""
    team_id: str = ""
    created_at: float = field(default_factory=time.time)

    @property
    def session_scope(self) -> str:
        """Prefix namespacing this workspace's shared runtime state.

        Conversations, memory sessions, and studio runs created for
        this workspace use this prefix, scoping shared memory/
        knowledge inside the single shared engines.
        """
        return f"ws:{self.workspace_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "name": self.name,
            "organization_id": self.organization_id,
            "team_id": self.team_id,
            "session_scope": self.session_scope,
            "created_at": self.created_at,
        }


@dataclass
class Organization:
    organization_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "organization_id": self.organization_id,
            "name": self.name,
            "created_at": self.created_at,
        }


@dataclass
class AuditEntry:
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    actor_id: str = ""
    action: str = ""
    resource: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "actor_id": self.actor_id,
            "action": self.action,
            "resource": self.resource,
            "detail": dict(self.detail),
        }


class EnterpriseEngine:
    """Organizations, teams, workspaces, members, RBAC, and audit."""

    def __init__(self, max_audit_entries: int = 10_000) -> None:
        if max_audit_entries < 1:
            raise ValueError("max_audit_entries must be >= 1")
        self._organizations: dict[str, Organization] = {}
        self._members: dict[str, Member] = {}
        self._teams: dict[str, Team] = {}
        self._workspaces: dict[str, Workspace] = {}
        self._audit: list[AuditEntry] = []
        self._max_audit = max_audit_entries

    # ── Bootstrap ───────────────────────────────────────────────

    def bootstrap_organization(
        self, org_name: str, owner_email: str, owner_name: str = ""
    ) -> tuple[Organization, Member]:
        """Create an organization with its first OWNER member.

        The only unauthenticated operation — everything after requires
        an actor.
        """
        if not org_name.strip():
            raise ValueError("organization name must not be empty")
        if not owner_email.strip():
            raise ValueError("owner email must not be empty")
        org = Organization(name=org_name.strip())
        owner = Member(
            email=owner_email.strip(),
            display_name=owner_name.strip() or owner_email.strip(),
            role=Role.OWNER,
            organization_id=org.organization_id,
        )
        self._organizations[org.organization_id] = org
        self._members[owner.member_id] = owner
        self._record(owner.member_id, "organization.bootstrap", org.organization_id,
                     {"name": org.name})
        return org, owner

    # ── Permission core ─────────────────────────────────────────

    def check_permission(self, actor_id: str, permission: Permission) -> None:
        """Raise PermissionDenied unless the actor holds `permission`."""
        actor = self._members.get(actor_id)
        if actor is None:
            raise NotFound(f"Member '{actor_id}' not found")
        if permission not in _ROLE_PERMISSIONS[actor.role]:
            raise PermissionDenied(
                f"Role '{actor.role.value}' lacks permission '{permission.value}'"
            )

    def get_permissions(self, member_id: str) -> list[str]:
        member = self._members.get(member_id)
        if member is None:
            raise NotFound(f"Member '{member_id}' not found")
        return sorted(p.value for p in _ROLE_PERMISSIONS[member.role])

    # ── Members ─────────────────────────────────────────────────

    def add_member(
        self,
        actor_id: str,
        email: str,
        display_name: str = "",
        role: Role = Role.MEMBER,
    ) -> Member:
        self.check_permission(actor_id, Permission.MANAGE_MEMBERS)
        actor = self._members[actor_id]
        if role == Role.OWNER and actor.role != Role.OWNER:
            raise PermissionDenied("Only an owner can grant the owner role")
        if not email.strip():
            raise ValueError("email must not be empty")
        member = Member(
            email=email.strip(),
            display_name=display_name.strip() or email.strip(),
            role=role,
            organization_id=actor.organization_id,
        )
        self._members[member.member_id] = member
        self._record(actor_id, "member.add", member.member_id,
                     {"email": member.email, "role": role.value})
        return member

    def change_role(self, actor_id: str, member_id: str, role: Role) -> Member:
        self.check_permission(actor_id, Permission.MANAGE_MEMBERS)
        actor = self._members[actor_id]
        member = self._members.get(member_id)
        if member is None:
            raise NotFound(f"Member '{member_id}' not found")
        if (role == Role.OWNER or member.role == Role.OWNER) and actor.role != Role.OWNER:
            raise PermissionDenied("Only an owner can change owner roles")
        previous = member.role
        member.role = role
        self._record(actor_id, "member.change_role", member_id,
                     {"from": previous.value, "to": role.value})
        return member

    def list_members(self, organization_id: str) -> list[Member]:
        return sorted(
            (m for m in self._members.values()
             if m.organization_id == organization_id),
            key=lambda m: m.created_at,
        )

    def get_member(self, member_id: str) -> Optional[Member]:
        return self._members.get(member_id)

    # ── Teams ───────────────────────────────────────────────────

    def create_team(self, actor_id: str, name: str) -> Team:
        self.check_permission(actor_id, Permission.MANAGE_TEAMS)
        if not name.strip():
            raise ValueError("team name must not be empty")
        actor = self._members[actor_id]
        team = Team(name=name.strip(), organization_id=actor.organization_id)
        self._teams[team.team_id] = team
        self._record(actor_id, "team.create", team.team_id, {"name": team.name})
        return team

    def add_to_team(self, actor_id: str, team_id: str, member_id: str) -> Team:
        self.check_permission(actor_id, Permission.MANAGE_TEAMS)
        team = self._teams.get(team_id)
        if team is None:
            raise NotFound(f"Team '{team_id}' not found")
        if member_id not in self._members:
            raise NotFound(f"Member '{member_id}' not found")
        team.member_ids.add(member_id)
        self._record(actor_id, "team.add_member", team_id, {"member_id": member_id})
        return team

    def remove_from_team(self, actor_id: str, team_id: str, member_id: str) -> Team:
        self.check_permission(actor_id, Permission.MANAGE_TEAMS)
        team = self._teams.get(team_id)
        if team is None:
            raise NotFound(f"Team '{team_id}' not found")
        team.member_ids.discard(member_id)
        self._record(actor_id, "team.remove_member", team_id, {"member_id": member_id})
        return team

    def list_teams(self, organization_id: str) -> list[Team]:
        return sorted(
            (t for t in self._teams.values()
             if t.organization_id == organization_id),
            key=lambda t: t.created_at,
        )

    def get_team(self, team_id: str) -> Optional[Team]:
        return self._teams.get(team_id)

    # ── Workspaces ──────────────────────────────────────────────

    def create_workspace(
        self, actor_id: str, name: str, team_id: str = ""
    ) -> Workspace:
        self.check_permission(actor_id, Permission.MANAGE_WORKSPACES)
        if not name.strip():
            raise ValueError("workspace name must not be empty")
        if team_id and team_id not in self._teams:
            raise NotFound(f"Team '{team_id}' not found")
        actor = self._members[actor_id]
        workspace = Workspace(
            name=name.strip(),
            organization_id=actor.organization_id,
            team_id=team_id,
        )
        self._workspaces[workspace.workspace_id] = workspace
        self._record(actor_id, "workspace.create", workspace.workspace_id,
                     {"name": workspace.name, "team_id": team_id})
        return workspace

    def list_workspaces(
        self, organization_id: str, team_id: str = ""
    ) -> list[Workspace]:
        workspaces = [
            w for w in self._workspaces.values()
            if w.organization_id == organization_id
        ]
        if team_id:
            workspaces = [w for w in workspaces if w.team_id == team_id]
        return sorted(workspaces, key=lambda w: w.created_at)

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        return self._workspaces.get(workspace_id)

    # ── Organizations & analytics ───────────────────────────────

    def list_organizations(self) -> list[Organization]:
        return sorted(self._organizations.values(), key=lambda o: o.created_at)

    def get_organization(self, organization_id: str) -> Optional[Organization]:
        return self._organizations.get(organization_id)

    def get_analytics(self, organization_id: str) -> dict[str, Any]:
        """Real counts for one organization — no invented metrics."""
        if organization_id not in self._organizations:
            raise NotFound(f"Organization '{organization_id}' not found")
        members = self.list_members(organization_id)
        return {
            "organization_id": organization_id,
            "members": len(members),
            "members_by_role": {
                role.value: sum(1 for m in members if m.role == role)
                for role in Role
            },
            "teams": len(self.list_teams(organization_id)),
            "workspaces": len(self.list_workspaces(organization_id)),
            "audit_entries": sum(
                1 for e in self._audit
                if self._members.get(e.actor_id) is not None
                and self._members[e.actor_id].organization_id == organization_id
            ),
        }

    # ── Audit ───────────────────────────────────────────────────

    def get_audit_log(
        self,
        actor_id: str = "",
        action_prefix: str = "",
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Audit entries, newest first, optionally filtered."""
        entries = self._audit
        if actor_id:
            entries = [e for e in entries if e.actor_id == actor_id]
        if action_prefix:
            entries = [e for e in entries if e.action.startswith(action_prefix)]
        return list(reversed(entries))[: max(0, limit)]

    def _record(
        self, actor_id: str, action: str, resource: str, detail: dict[str, Any]
    ) -> None:
        self._audit.append(
            AuditEntry(actor_id=actor_id, action=action, resource=resource,
                       detail=detail)
        )
        if len(self._audit) > self._max_audit:
            self._audit = self._audit[-self._max_audit:]

    def clear(self) -> None:
        """Drop all state. For testing."""
        self._organizations.clear()
        self._members.clear()
        self._teams.clear()
        self._workspaces.clear()
        self._audit.clear()
