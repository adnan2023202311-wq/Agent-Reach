"""Tests for M9.5 — Live Provider Runtime.

Verifies that /api/v1/providers exposes real runtime information per
provider (health, capabilities, usage from persisted traces, cost
estimates from the router cost model) while keeping the M8 summary
shape backward compatible.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from config.settings import KNOWN_PROVIDERS, get_settings


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


class TestProvidersBackwardCompat:
    def test_m8_summary_shape_unchanged(self, client: TestClient) -> None:
        resp = client.get("/api/v1/providers")
        assert resp.status_code == 200
        providers = resp.json()
        assert len(providers) == len(KNOWN_PROVIDERS)
        for p in providers:
            assert set(p.keys()) == {"id", "status", "enabled"}

    def test_patch_still_501(self, client: TestClient) -> None:
        assert client.patch("/api/v1/providers/anthropic").status_code == 501


class TestProvidersRuntime:
    def test_runtime_block_for_every_provider(self, client: TestClient) -> None:
        resp = client.get("/api/v1/providers/runtime")
        assert resp.status_code == 200
        data = resp.json()
        # Every settings-known provider is present…
        assert set(KNOWN_PROVIDERS) <= set(data.keys())
        for provider_id, info in data.items():
            for key in ("configured", "available", "default_model", "capabilities", "health", "usage", "cost"):
                assert key in info, f"{provider_id} missing {key}"

    def test_router_only_providers_included(self, client: TestClient) -> None:
        """M9.5: providers known only to the router (no settings key)
        must still expose runtime info — e.g. ollama."""
        data = client.get("/api/v1/providers/runtime").json()
        assert "ollama" in data
        assert data["ollama"]["configured"] is False
        # ollama is the router's zero-cost local provider
        assert data["ollama"]["cost"]["per_1k_tokens"] == 0.0

    def test_single_router_only_provider_detail(self, client: TestClient) -> None:
        resp = client.get("/api/v1/providers/ollama")
        assert resp.status_code == 200
        assert resp.json()["id"] == "ollama"

    def test_health_fields_present(self, client: TestClient) -> None:
        data = client.get("/api/v1/providers/runtime").json()
        health = data["anthropic"]["health"]
        for key in ("healthy", "success_rate", "avg_latency_ms", "total_calls", "last_error"):
            assert key in health

    def test_capabilities_from_router(self, client: TestClient) -> None:
        data = client.get("/api/v1/providers/runtime").json()
        assert "reasoning" in data["anthropic"]["capabilities"]
        # settings name "google" maps to router name "gemini"
        assert "long_context" in data["google"]["capabilities"]

    def test_unconfigured_reports_honestly(self, client: TestClient) -> None:
        data = client.get("/api/v1/providers/runtime").json()
        # No API keys in the test env → nothing is configured.
        assert all(info["configured"] is False for info in data.values())
        assert all(info["available"] is False for info in data.values())

    def test_usage_tracks_real_traffic(self, client: TestClient) -> None:
        client.post("/api/v1/chat", json={"message": "Use a provider"})
        data = client.get("/api/v1/providers/runtime").json()
        total_requests = sum(info["usage"]["requests"] for info in data.values())
        assert total_requests >= 1

    def test_cost_is_labeled_estimate(self, client: TestClient) -> None:
        data = client.get("/api/v1/providers/runtime").json()
        assert "estimate" in data["anthropic"]["cost"]["note"].lower()


class TestSingleProvider:
    def test_get_known_provider(self, client: TestClient) -> None:
        resp = client.get("/api/v1/providers/anthropic")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "anthropic"
        assert data["default_model"]
        assert "health" in data

    def test_unknown_provider_404(self, client: TestClient) -> None:
        assert client.get("/api/v1/providers/skynet").status_code == 404
