"""Tests for M9.12 — AI Engineering Organization.

Proves: valid role graph with wave scheduling (CEO first, Release
Manager last), every role executing through the REAL shared pipeline
(persisted trace per role), upstream deliverables flowing as real M3
messages, honest partial/failed statuses, graph validation, and the
/api/v1/organization endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agents.organization import (
    ORGANIZATION_ROLES,
    EngineeringOrganization,
    RoleSpec,
)
from api.main import create_app
from composition import build_intelligent_pipeline
from config.settings import get_settings


# ===========================================================================
# Structure
# ===========================================================================


class TestOrganizationStructure:
    def test_chart_has_all_m912_roles(self) -> None:
        organization = EngineeringOrganization(build_intelligent_pipeline())
        chart = organization.describe()
        roles = {r["role"] for r in chart["roles"]}
        assert roles == {
            "ceo", "architect", "planner", "backend_engineer",
            "frontend_engineer", "research", "qa", "security",
            "devops", "documentation", "release_manager",
        }

    def test_waves_order_ceo_first_release_last(self) -> None:
        organization = EngineeringOrganization(build_intelligent_pipeline())
        waves = organization.describe()["waves"]
        assert waves[0] == ["ceo"]
        assert waves[-1] == ["release_manager"]
        # engineers run concurrently in one wave
        engineer_wave = next(
            w for w in waves if "backend_engineer" in w
        )
        assert "frontend_engineer" in engineer_wave

    def test_duplicate_roles_rejected(self) -> None:
        with pytest.raises(ValueError, match="Duplicate"):
            EngineeringOrganization(
                build_intelligent_pipeline(),
                roles=(RoleSpec("a", "x"), RoleSpec("a", "y")),
            )

    def test_unknown_dependency_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown roles"):
            EngineeringOrganization(
                build_intelligent_pipeline(),
                roles=(RoleSpec("a", "x", depends_on=("ghost",)),),
            )

    def test_cycle_rejected_at_run(self) -> None:
        organization = EngineeringOrganization(
            build_intelligent_pipeline(),
            roles=(
                RoleSpec("a", "x", depends_on=("b",)),
                RoleSpec("b", "y", depends_on=("a",)),
            ),
        )
        with pytest.raises(ValueError, match="cycle"):
            organization.describe()


# ===========================================================================
# Execution
# ===========================================================================


@pytest.mark.asyncio
class TestProjectExecution:
    def _small_org(self, pipeline) -> EngineeringOrganization:
        """Three-role organization keeps tests fast while covering
        the full mechanics (dependency, sharing, waves)."""
        return EngineeringOrganization(
            pipeline,
            roles=(
                RoleSpec("ceo", "You are the CEO. Define the objective."),
                RoleSpec("architect", "You are the Architect.", depends_on=("ceo",)),
                RoleSpec("qa", "You are QA.", depends_on=("architect",)),
            ),
        )

    async def test_every_role_runs_through_real_pipeline(self) -> None:
        pipeline = build_intelligent_pipeline()
        organization = self._small_org(pipeline)
        record = await organization.run_project("Build a search feature")
        assert record.status == "succeeded"
        for role, run in record.role_runs.items():
            assert run.status == "succeeded", role
            assert run.deliverable
            # each role's execution is a REAL persisted trace
            assert pipeline.get_trace(run.request_id) is not None
            assert run.latency_ms > 0

    async def test_deliverables_flow_as_real_messages(self) -> None:
        pipeline = build_intelligent_pipeline()
        organization = self._small_org(pipeline)
        record = await organization.run_project("Ship the thing")
        # ceo→architect and architect→qa
        assert record.messages_exchanged == 2
        communications = organization.get_communications(record.project_id)
        assert len(communications) == 2
        assert communications[0]["sender"] == "role:ceo"
        assert communications[0]["recipient"] == "role:architect"

    async def test_full_organization_runs(self) -> None:
        pipeline = build_intelligent_pipeline()
        organization = EngineeringOrganization(pipeline)
        record = await organization.run_project("Launch the analytics module")
        assert record.status == "succeeded"
        assert len(record.role_runs) == len(ORGANIZATION_ROLES)
        # 12 upstream edges in the default chart
        assert record.messages_exchanged == sum(
            len(spec.depends_on) for spec in ORGANIZATION_ROLES
        )

    async def test_role_failure_isolated_and_status_partial(self) -> None:
        class _FlakyPipeline:
            def __init__(self, real) -> None:
                self._real = real
                self.calls = 0

            async def process(self, message, **kwargs):
                self.calls += 1
                if "Architect" in message:
                    raise RuntimeError("architect provider down")
                return await self._real.process(message, **kwargs)

        real = build_intelligent_pipeline()
        organization = self._small_org(_FlakyPipeline(real))
        record = await organization.run_project("Survive failures")
        assert record.status == "partial"
        assert record.role_runs["ceo"].status == "succeeded"
        assert record.role_runs["architect"].status == "failed"
        assert "architect provider down" in record.role_runs["architect"].error

    async def test_empty_objective_rejected(self) -> None:
        organization = self._small_org(build_intelligent_pipeline())
        with pytest.raises(ValueError):
            await organization.run_project("   ")

    async def test_project_history(self) -> None:
        organization = self._small_org(build_intelligent_pipeline())
        first = await organization.run_project("first")
        second = await organization.run_project("second")
        projects = organization.list_projects()
        assert [p.project_id for p in projects] == [
            second.project_id, first.project_id,
        ]
        assert organization.get_project(first.project_id) is first


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


class TestOrganizationAPI:
    def test_chart_endpoint(self, client: TestClient) -> None:
        chart = client.get("/api/v1/organization/chart").json()
        assert len(chart["roles"]) == 11
        assert chart["waves"][0] == ["ceo"]

    def test_project_run_and_detail(self, client: TestClient) -> None:
        record = client.post(
            "/api/v1/organization/projects",
            json={"objective": "Build the reporting dashboard"},
        ).json()
        assert record["status"] == "succeeded"
        assert len(record["role_runs"]) == 11
        # role traces observable in the observatory
        ceo_request = record["role_runs"]["ceo"]["request_id"]
        assert (
            client.get(f"/api/v1/observatory/trace/{ceo_request}").status_code
            == 200
        )
        detail = client.get(
            f"/api/v1/organization/projects/{record['project_id']}"
        )
        assert detail.status_code == 200

    def test_communications_endpoint(self, client: TestClient) -> None:
        record = client.post(
            "/api/v1/organization/projects",
            json={"objective": "Small internal tool"},
        ).json()
        comms = client.get(
            f"/api/v1/organization/projects/{record['project_id']}/communications"
        ).json()
        assert comms["count"] == record["messages_exchanged"]

    def test_unknown_project_404(self, client: TestClient) -> None:
        assert (
            client.get("/api/v1/organization/projects/ghost").status_code == 404
        )

    def test_empty_objective_422(self, client: TestClient) -> None:
        assert (
            client.post(
                "/api/v1/organization/projects", json={"objective": ""}
            ).status_code
            == 422
        )
