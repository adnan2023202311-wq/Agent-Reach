"""Tests for M9.4 — Live Dashboard.

Verifies that /api/v1/dashboard and /api/v1/dashboard/runtime report
real runtime statistics sourced from the IntelligentPipeline's trace
store, the SessionManager, and each subsystem's get_stats() — and
that fresh processes report honest zeros, not fabricated activity.
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


class TestDashboardFreshBoot:
    def test_snapshot_has_runtime_section(self, client: TestClient) -> None:
        resp = client.get("/api/v1/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "runtime" in data
        runtime = data["runtime"]
        # M9.4 required metrics are present.
        for key in (
            "active_conversations",
            "pipeline_requests",
            "provider_usage",
            "memory_size",
            "knowledge_nodes",
            "learning_records",
            "reflection_executions",
            "router_decisions",
            "errors",
            "avg_latency_ms",
            "token_usage",
            "estimated_cost",
        ):
            assert key in runtime, f"missing runtime metric: {key}"

    def test_fresh_boot_reports_honest_zeros(self, client: TestClient) -> None:
        runtime = client.get("/api/v1/dashboard/runtime").json()
        assert runtime["pipeline_requests"] == 0
        assert runtime["errors"] == 0
        assert runtime["router_decisions"] == 0
        assert runtime["provider_usage"] == {}

    def test_activity_and_recent_chats_empty_on_boot(self, client: TestClient) -> None:
        data = client.get("/api/v1/dashboard").json()
        assert data["activity"] == []
        assert data["recent_chats"] == []


class TestDashboardAfterActivity:
    def test_chat_increments_pipeline_requests(self, client: TestClient) -> None:
        client.post("/api/v1/chat", json={"message": "Hello dashboard"})
        runtime = client.get("/api/v1/dashboard/runtime").json()
        assert runtime["pipeline_requests"] >= 1

    def test_activity_feed_shows_real_executions(self, client: TestClient) -> None:
        chat = client.post("/api/v1/chat", json={"message": "Track me"}).json()
        data = client.get("/api/v1/dashboard").json()
        assert len(data["activity"]) >= 1
        request_ids = [a["request_id"] for a in data["activity"]]
        assert chat["request_id"] in request_ids
        entry = next(a for a in data["activity"] if a["request_id"] == chat["request_id"])
        assert entry["latency_ms"] > 0

    def test_memory_grows_with_usage(self, client: TestClient) -> None:
        before = client.get("/api/v1/dashboard/runtime").json()["memory_size"]
        client.post("/api/v1/chat", json={"message": "Remember this fact"})
        after = client.get("/api/v1/dashboard/runtime").json()["memory_size"]
        assert after > before

    def test_knowledge_nodes_grow_with_usage(self, client: TestClient) -> None:
        before = client.get("/api/v1/dashboard/runtime").json()["knowledge_nodes"]
        client.post("/api/v1/chat", json={"message": "Research knowledge graphs"})
        after = client.get("/api/v1/dashboard/runtime").json()["knowledge_nodes"]
        assert after > before

    def test_learning_records_grow_with_usage(self, client: TestClient) -> None:
        before = client.get("/api/v1/dashboard/runtime").json()["learning_records"]
        client.post("/api/v1/chat", json={"message": "Learn from this"})
        after = client.get("/api/v1/dashboard/runtime").json()["learning_records"]
        assert after > before

    def test_provider_usage_reflects_router_decisions(self, client: TestClient) -> None:
        client.post("/api/v1/chat", json={"message": "Route me"})
        runtime = client.get("/api/v1/dashboard/runtime").json()
        assert runtime["router_decisions"] >= 1
        assert sum(runtime["provider_usage"].values()) == runtime["router_decisions"]

    def test_recent_chats_shows_created_sessions(self, client: TestClient) -> None:
        created = client.post("/api/v1/conversations/sessions", json={}).json()
        data = client.get("/api/v1/dashboard").json()
        ids = [c["session_id"] for c in data["recent_chats"]]
        assert created["session_id"] in ids

    def test_subsystem_stats_are_real(self, client: TestClient) -> None:
        client.post("/api/v1/chat", json={"message": "Populate subsystems"})
        runtime = client.get("/api/v1/dashboard/runtime").json()
        subsystems = runtime["subsystems"]
        assert subsystems["memory"]["memory_counts"]["total"] >= 1
        assert subsystems["learning"]["total_executions"] >= 1
        assert "providers" in subsystems["router"]


class TestDashboardBackwardCompatibility:
    def test_m8_fields_still_present(self, client: TestClient) -> None:
        """Previous milestone consumers still get their fields."""
        data = client.get("/api/v1/dashboard").json()
        for key in ("activity", "recent_chats", "active_agents", "tools"):
            assert key in data
        assert isinstance(data["active_agents"], list)
        assert len(data["active_agents"]) >= 1
