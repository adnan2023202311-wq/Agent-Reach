"""Tests for M9.23 — Enterprise Intelligence Platform.

Proves: bootstrap flow, ENFORCED RBAC (viewer/member denied
management; only owners grant/revoke owner), teams and membership,
workspaces with session scopes, real analytics counts, and a real
append-only audit log — plus the /api/v1/collaboration endpoints
including honest 401/403/404/422 responses.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from config.settings import get_settings
from enterprise import (
    EnterpriseEngine,
    NotFound,
    Permission,
    PermissionDenied,
    Role,
)


def _bootstrapped() -> tuple[EnterpriseEngine, str, str]:
    engine = EnterpriseEngine()
    org, owner = engine.bootstrap_organization("Acme", "owner@acme.io", "Owner")
    return engine, org.organization_id, owner.member_id


# ===========================================================================
# RBAC
# ===========================================================================


class TestRBAC:
    def test_bootstrap_creates_owner(self) -> None:
        engine, org_id, owner_id = _bootstrapped()
        owner = engine.get_member(owner_id)
        assert owner.role == Role.OWNER
        assert engine.get_permissions(owner_id) == sorted(
            p.value for p in Permission
        )

    def test_viewer_cannot_manage(self) -> None:
        engine, _, owner_id = _bootstrapped()
        viewer = engine.add_member(owner_id, "v@acme.io", role=Role.VIEWER)
        with pytest.raises(PermissionDenied):
            engine.create_team(viewer.member_id, "Rogue Team")
        with pytest.raises(PermissionDenied):
            engine.add_member(viewer.member_id, "x@acme.io")
        with pytest.raises(PermissionDenied):
            engine.create_workspace(viewer.member_id, "Rogue WS")

    def test_member_can_execute_not_manage(self) -> None:
        engine, _, owner_id = _bootstrapped()
        member = engine.add_member(owner_id, "m@acme.io", role=Role.MEMBER)
        engine.check_permission(member.member_id, Permission.EXECUTE)  # ok
        with pytest.raises(PermissionDenied):
            engine.check_permission(member.member_id, Permission.MANAGE_TEAMS)

    def test_admin_cannot_grant_owner(self) -> None:
        engine, _, owner_id = _bootstrapped()
        admin = engine.add_member(owner_id, "a@acme.io", role=Role.ADMIN)
        with pytest.raises(PermissionDenied):
            engine.add_member(admin.member_id, "sneaky@acme.io", role=Role.OWNER)
        member = engine.add_member(admin.member_id, "m2@acme.io")
        with pytest.raises(PermissionDenied):
            engine.change_role(admin.member_id, member.member_id, Role.OWNER)

    def test_admin_cannot_demote_owner(self) -> None:
        engine, _, owner_id = _bootstrapped()
        admin = engine.add_member(owner_id, "a@acme.io", role=Role.ADMIN)
        with pytest.raises(PermissionDenied):
            engine.change_role(admin.member_id, owner_id, Role.MEMBER)

    def test_owner_can_promote(self) -> None:
        engine, _, owner_id = _bootstrapped()
        member = engine.add_member(owner_id, "m@acme.io")
        updated = engine.change_role(owner_id, member.member_id, Role.ADMIN)
        assert updated.role == Role.ADMIN

    def test_unknown_actor_not_found(self) -> None:
        engine, _, _ = _bootstrapped()
        with pytest.raises(NotFound):
            engine.check_permission("ghost", Permission.READ)


# ===========================================================================
# Teams / workspaces / analytics / audit
# ===========================================================================


class TestEnterpriseState:
    def test_team_lifecycle(self) -> None:
        engine, org_id, owner_id = _bootstrapped()
        team = engine.create_team(owner_id, "Engineering")
        member = engine.add_member(owner_id, "dev@acme.io")
        engine.add_to_team(owner_id, team.team_id, member.member_id)
        assert member.member_id in engine.get_team(team.team_id).member_ids
        engine.remove_from_team(owner_id, team.team_id, member.member_id)
        assert member.member_id not in engine.get_team(team.team_id).member_ids

    def test_team_unknown_member_rejected(self) -> None:
        engine, _, owner_id = _bootstrapped()
        team = engine.create_team(owner_id, "QA")
        with pytest.raises(NotFound):
            engine.add_to_team(owner_id, team.team_id, "ghost")

    def test_workspace_session_scope(self) -> None:
        engine, org_id, owner_id = _bootstrapped()
        team = engine.create_team(owner_id, "Research")
        workspace = engine.create_workspace(owner_id, "Lab", team_id=team.team_id)
        assert workspace.session_scope == f"ws:{workspace.workspace_id}"
        assert engine.list_workspaces(org_id, team_id=team.team_id) == [workspace]

    def test_workspace_unknown_team_rejected(self) -> None:
        engine, _, owner_id = _bootstrapped()
        with pytest.raises(NotFound):
            engine.create_workspace(owner_id, "WS", team_id="ghost")

    def test_analytics_reflect_real_counts(self) -> None:
        engine, org_id, owner_id = _bootstrapped()
        engine.add_member(owner_id, "a@acme.io", role=Role.ADMIN)
        engine.add_member(owner_id, "b@acme.io")
        engine.create_team(owner_id, "T1")
        engine.create_workspace(owner_id, "W1")
        analytics = engine.get_analytics(org_id)
        assert analytics["members"] == 3
        assert analytics["members_by_role"]["owner"] == 1
        assert analytics["members_by_role"]["admin"] == 1
        assert analytics["teams"] == 1
        assert analytics["workspaces"] == 1
        assert analytics["audit_entries"] >= 4

    def test_audit_appended_by_real_operations_only(self) -> None:
        engine, _, owner_id = _bootstrapped()
        baseline = len(engine.get_audit_log(limit=1000))
        engine.create_team(owner_id, "Audited")
        entries = engine.get_audit_log(limit=1000)
        assert len(entries) == baseline + 1
        assert entries[0].action == "team.create"  # newest first
        assert entries[0].actor_id == owner_id

    def test_audit_filters(self) -> None:
        engine, _, owner_id = _bootstrapped()
        engine.create_team(owner_id, "T")
        engine.add_member(owner_id, "x@acme.io")
        team_entries = engine.get_audit_log(action_prefix="team.")
        assert all(e.action.startswith("team.") for e in team_entries)
        actor_entries = engine.get_audit_log(actor_id=owner_id)
        assert all(e.actor_id == owner_id for e in actor_entries)

    def test_validation(self) -> None:
        engine, _, owner_id = _bootstrapped()
        with pytest.raises(ValueError):
            engine.create_team(owner_id, "  ")
        with pytest.raises(ValueError):
            engine.add_member(owner_id, "  ")
        with pytest.raises(ValueError):
            EnterpriseEngine(max_audit_entries=0)


# ===========================================================================
# API
# ===========================================================================


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    import config.settings as settings_module

    original = settings_module.get_settings
    settings_module.get_settings = lambda: settings_module.Settings(
        anthropic_api_key=None,
        default_model_provider="anthropic",
    )
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    settings_module.get_settings = original
    get_settings.cache_clear()


def _bootstrap_api(client: TestClient) -> tuple[str, str]:
    data = client.post(
        "/api/v1/collaboration/bootstrap",
        json={"organization_name": "Acme", "owner_email": "owner@acme.io"},
    ).json()
    return data["organization"]["organization_id"], data["owner"]["member_id"]


class TestCollaborationAPI:
    def test_fresh_boot_no_fake_data(self, client: TestClient) -> None:
        """The M8 mock served hardcoded orgs/teams/audit. Must be
        honestly empty now."""
        assert client.get("/api/v1/collaboration/organizations").json()["count"] == 0
        assert client.get("/api/v1/collaboration/teams").json()["count"] == 0
        assert client.get("/api/v1/collaboration/audit").json()["count"] == 0

    def test_bootstrap_and_full_flow(self, client: TestClient) -> None:
        org_id, owner_id = _bootstrap_api(client)
        headers = {"X-Member-Id": owner_id}

        team = client.post(
            "/api/v1/collaboration/teams", json={"name": "Engineering"},
            headers=headers,
        ).json()
        member = client.post(
            "/api/v1/collaboration/members",
            json={"email": "dev@acme.io", "role": "member"},
            headers=headers,
        ).json()
        added = client.post(
            f"/api/v1/collaboration/teams/{team['team_id']}/members",
            json={"member_id": member["member_id"]},
            headers=headers,
        ).json()
        assert member["member_id"] in added["member_ids"]

        workspace = client.post(
            "/api/v1/collaboration/workspaces",
            json={"name": "Lab", "team_id": team["team_id"]},
            headers=headers,
        ).json()
        assert workspace["session_scope"].startswith("ws:")

        analytics = client.get(
            f"/api/v1/collaboration/organizations/{org_id}/analytics"
        ).json()
        assert analytics["members"] == 2
        assert analytics["teams"] == 1
        assert analytics["workspaces"] == 1

        audit = client.get("/api/v1/collaboration/audit").json()
        actions = [e["action"] for e in audit["items"]]
        assert "team.create" in actions
        assert "workspace.create" in actions

    def test_missing_actor_401(self, client: TestClient) -> None:
        _bootstrap_api(client)
        resp = client.post("/api/v1/collaboration/teams", json={"name": "T"})
        assert resp.status_code == 401

    def test_forbidden_403(self, client: TestClient) -> None:
        _, owner_id = _bootstrap_api(client)
        viewer = client.post(
            "/api/v1/collaboration/members",
            json={"email": "v@acme.io", "role": "viewer"},
            headers={"X-Member-Id": owner_id},
        ).json()
        resp = client.post(
            "/api/v1/collaboration/teams",
            json={"name": "Rogue"},
            headers={"X-Member-Id": viewer["member_id"]},
        )
        assert resp.status_code == 403

    def test_invalid_role_422(self, client: TestClient) -> None:
        _, owner_id = _bootstrap_api(client)
        resp = client.post(
            "/api/v1/collaboration/members",
            json={"email": "x@acme.io", "role": "emperor"},
            headers={"X-Member-Id": owner_id},
        )
        assert resp.status_code == 422

    def test_unknown_entities_404(self, client: TestClient) -> None:
        _, owner_id = _bootstrap_api(client)
        headers = {"X-Member-Id": owner_id}
        assert (
            client.post(
                "/api/v1/collaboration/teams/ghost/members",
                json={"member_id": owner_id},
                headers=headers,
            ).status_code
            == 404
        )
        assert (
            client.get(
                "/api/v1/collaboration/organizations/ghost/analytics"
            ).status_code
            == 404
        )

    def test_permissions_endpoint(self, client: TestClient) -> None:
        _, owner_id = _bootstrap_api(client)
        data = client.get(
            f"/api/v1/collaboration/members/{owner_id}/permissions"
        ).json()
        assert "manage_organization" in data["permissions"]
