"""Integration tests for /api/v1/workflows endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from config.settings import Settings, get_settings
from workflows.models import StepType, Workflow, WorkflowStep


@pytest.fixture(autouse=True)
def _clear_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    settings = Settings(anthropic_api_key="test-key-for-api-tests")
    get_settings.cache_clear()
    import config.settings as settings_module
    settings_module.get_settings = lambda: settings
    # Mock the AnthropicModelClient so workflow runs don't hit the real API.
    with patch("infrastructure.model_client.AnthropicModelClient") as mock_cls:
        mock_instance = mock_cls.return_value
        mock_instance.complete = AsyncMock(return_value="mocked response")
        from api.main import create_app
        app = create_app()
        with TestClient(app) as c:
            yield c
    get_settings.cache_clear()


def _register_sample_workflow(client: TestClient) -> None:
    """Register a sample workflow directly on the registry."""
    wf = Workflow(
        name="test-wf",
        description="A test workflow",
        variables={"x": 5},
        steps=[
            WorkflowStep(
                step_id="s1",
                type=StepType.AGENT,
                target="research",
                inputs={"q": "hello"},
                output_keys=["text"],
            ),
        ],
        outputs={"result": "outputs.s1.text"},
    )
    client.app.state.workflow_registry.register(wf)


class TestWorkflowList:
    def test_list_workflows_empty(self, client: TestClient) -> None:
        resp = client.get("/api/v1/workflows")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_workflows_populated(self, client: TestClient) -> None:
        _register_sample_workflow(client)
        resp = client.get("/api/v1/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test-wf"


class TestWorkflowGet:
    def test_get_workflow(self, client: TestClient) -> None:
        _register_sample_workflow(client)
        resp = client.get("/api/v1/workflows/test-wf")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-wf"

    def test_get_workflow_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/workflows/ghost")
        assert resp.status_code == 404


class TestWorkflowRun:
    def test_run_workflow(self, client: TestClient) -> None:
        _register_sample_workflow(client)
        resp = client.post("/api/v1/workflows/test-wf/run", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] in ("completed", "failed")

    def test_run_workflow_not_found(self, client: TestClient) -> None:
        resp = client.post("/api/v1/workflows/ghost/run", json={})
        assert resp.status_code == 404


class TestWorkflowRuns:
    def test_list_runs(self, client: TestClient) -> None:
        resp = client.get("/api/v1/workflows/runs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_run(self, client: TestClient) -> None:
        _register_sample_workflow(client)
        run_resp = client.post("/api/v1/workflows/test-wf/run", json={})
        assert run_resp.status_code == 200
        workflow_id = run_resp.json()["workflow_id"]
        resp = client.get(f"/api/v1/workflows/runs/{workflow_id}")
        assert resp.status_code == 200

    def test_get_run_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/workflows/runs/ghost")
        assert resp.status_code == 404
