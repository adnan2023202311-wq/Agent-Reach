"""Tests for M9.22 — real Marketplace API.

The M8 router returned a hardcoded catalog with invented download
counts and always-successful install/uninstall. M9 wires the REAL
PluginMarketplace engine, seeded from the live tool registry. These
tests prove: real seeding, real state transitions, honest 404s,
compatibility gating, search/status filters, and stats.
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


class TestMarketplaceCatalog:
    def test_catalog_seeded_from_live_tool_registry(self, client: TestClient) -> None:
        data = client.get("/api/v1/marketplace/plugins").json()
        ids = {p["plugin_id"] for p in data["items"]}
        # Production tools registered in M9.6 appear as plugins.
        assert {"http_request", "rss_fetch", "browser_fetch", "fs_read"} <= ids
        # The M8 fake entries are gone.
        assert "slack_bridge" not in ids
        assert "notion_sync" not in ids

    def test_no_fabricated_popularity_metrics(self, client: TestClient) -> None:
        data = client.get("/api/v1/marketplace/plugins").json()
        for plugin in data["items"]:
            assert "downloads" not in plugin
            assert "rating" not in plugin

    def test_enabled_tools_seed_as_installed(self, client: TestClient) -> None:
        data = client.get("/api/v1/marketplace/plugins").json()
        by_id = {p["plugin_id"]: p for p in data["items"]}
        assert by_id["http_request"]["status"] == "installed"
        # telegram_send is disabled without a token → available
        assert by_id["telegram_send"]["status"] == "available"

    def test_status_filter(self, client: TestClient) -> None:
        data = client.get("/api/v1/marketplace/plugins?status=installed").json()
        assert data["count"] >= 1
        assert all(p["status"] == "installed" for p in data["items"])

    def test_invalid_status_422(self, client: TestClient) -> None:
        assert (
            client.get("/api/v1/marketplace/plugins?status=imaginary").status_code
            == 422
        )

    def test_search(self, client: TestClient) -> None:
        data = client.get("/api/v1/marketplace/plugins?query=rss").json()
        assert data["count"] >= 1
        assert any(p["plugin_id"] == "rss_fetch" for p in data["items"])

    def test_stats_reflect_reality(self, client: TestClient) -> None:
        stats = client.get("/api/v1/marketplace/plugins/stats").json()
        assert stats["total"] >= 7  # the seeded production tools
        assert stats["installed"] >= 1


class TestMarketplaceLifecycle:
    def test_get_single_plugin_with_compatibility(self, client: TestClient) -> None:
        data = client.get("/api/v1/marketplace/plugins/http_request").json()
        assert data["plugin_id"] == "http_request"
        assert data["compatible"] is True
        assert data["compatibility_problems"] == []

    def test_get_unknown_404(self, client: TestClient) -> None:
        assert (
            client.get("/api/v1/marketplace/plugins/warp_drive").status_code == 404
        )

    def test_uninstall_then_install_roundtrip(self, client: TestClient) -> None:
        off = client.delete("/api/v1/marketplace/plugins/rss_fetch")
        assert off.status_code == 200
        assert off.json()["status"] == "available"

        on = client.post(
            "/api/v1/marketplace/plugins/install", json={"plugin_id": "rss_fetch"}
        )
        assert on.status_code == 200
        assert on.json()["status"] == "installed"
        assert on.json()["installed_at"]  # real timestamp

    def test_install_unknown_404_no_fake_success(self, client: TestClient) -> None:
        """The M8 mock returned 'installed' for ANY id. Must 404 now."""
        resp = client.post(
            "/api/v1/marketplace/plugins/install", json={"plugin_id": "ghost"}
        )
        assert resp.status_code == 404

    def test_uninstall_unknown_404(self, client: TestClient) -> None:
        assert (
            client.delete("/api/v1/marketplace/plugins/ghost").status_code == 404
        )

    def test_updates_endpoint_honest_empty(self, client: TestClient) -> None:
        data = client.get("/api/v1/marketplace/plugins/updates").json()
        # Fresh boot: no updates pending — real zero.
        assert data["count"] == 0
