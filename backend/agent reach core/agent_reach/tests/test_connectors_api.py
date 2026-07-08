"""Tests for M9.1 — real Connectors API.

The M8 mock advertised 13 unimplemented integrations and a /test that
returned "connected"/87ms for anything. These tests prove the list is
derived from the real runtime, tests execute the real backing tools
(recorded in ToolRuntime history), and unprovable tests are refused.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from config.settings import get_settings


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


class TestConnectorCatalog:
    def test_catalog_derived_from_runtime(self, client: TestClient) -> None:
        data = client.get("/api/v1/connectors").json()
        ids = {c["id"] for c in data["items"]}
        assert {"http", "rss", "browser", "filesystem", "telegram", "mcp"} == ids
        # The M8 fictional integrations are gone.
        assert "notion" not in ids
        assert "slack" not in ids

    def test_status_mirrors_real_tool_state(self, client: TestClient) -> None:
        data = client.get("/api/v1/connectors").json()
        by_id = {c["id"]: c for c in data["items"]}
        assert by_id["http"]["status"] == "ready"
        # telegram tool is disabled without TELEGRAM_BOT_TOKEN
        assert by_id["telegram"]["status"] == "disabled"

    def test_detail_includes_real_metrics(self, client: TestClient) -> None:
        detail = client.get("/api/v1/connectors/filesystem").json()
        assert detail["backing_tool"] == "fs_list"
        assert detail["metrics"]["total_executions"] == 0  # honest zero

    def test_unknown_connector_404(self, client: TestClient) -> None:
        assert client.get("/api/v1/connectors/notion").status_code == 404


class TestConnectorTests:
    def test_filesystem_test_actually_executes(self, client: TestClient) -> None:
        resp = client.post("/api/v1/connectors/filesystem/test", json={})
        assert resp.status_code == 200
        result = resp.json()
        assert result["success"] is True
        assert result["latency_ms"] > 0  # measured
        assert result["execution_id"]
        # It really went through the ToolRuntime — history shows it.
        history = client.get("/api/v1/tools/history?tool_id=fs_list").json()
        assert history["count"] >= 1

    def test_parameterless_http_test_refused(self, client: TestClient) -> None:
        """No fake success: an HTTP test without a URL cannot prove
        connectivity, so it is rejected."""
        resp = client.post("/api/v1/connectors/http/test", json={})
        assert resp.status_code == 422
        assert resp.json()["message"].startswith("Connector 'http' needs")

    def test_failed_test_reports_failure(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/connectors/filesystem/test",
            json={"parameters": {"path": "no/such/dir"}},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["success"] is False
        assert result["error"]

    def test_mcp_test_reports_runtime_state(self, client: TestClient) -> None:
        resp = client.post("/api/v1/connectors/mcp/test", json={})
        assert resp.status_code == 200
        result = resp.json()
        assert result["success"] is True
        assert "0 tools registered" in result["detail"]

    def test_unknown_connector_test_404(self, client: TestClient) -> None:
        assert (
            client.post("/api/v1/connectors/ghost/test", json={}).status_code
            == 404
        )
