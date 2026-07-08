"""API tests for M9.20 — /api/v1/prompts (Prompt Studio + Evolution).

The M8 router probed for library methods that never existed, fell
back to a module-level dict, and served a hardcoded optimize stub
with an invented '+12%'. These tests prove the real engine is wired:
library-backed CRUD, real rendering, usage-evidence recording,
evidence-gated proposals, apply, history, and rollback.
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


def _create(client: TestClient, name: str = "researcher",
            template: str = "Research {{topic}} and report.") -> dict:
    resp = client.post(
        "/api/v1/prompts",
        json={"name": name, "template": template, "tags": ["research"]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestPromptCrud:
    def test_create_and_get(self, client: TestClient) -> None:
        created = _create(client)
        assert created["version"] == 1
        prompt = client.get("/api/v1/prompts/researcher").json()
        assert prompt["template"] == "Research {{topic}} and report."
        assert prompt["variables"] == ["topic"]

    def test_re_register_bumps_version(self, client: TestClient) -> None:
        _create(client)
        second = _create(client, template="Research {{topic}} deeply.")
        assert second["version"] == 2

    def test_get_unknown_404(self, client: TestClient) -> None:
        assert client.get("/api/v1/prompts/ghost").status_code == 404

    def test_list_with_search_and_tag(self, client: TestClient) -> None:
        _create(client)
        _create(client, name="coder", template="Write code for {{task}}.")
        all_items = client.get("/api/v1/prompts").json()
        assert all_items["count"] == 2
        searched = client.get("/api/v1/prompts?search=code").json()
        assert searched["count"] == 1
        tagged = client.get("/api/v1/prompts?tag=research").json()
        assert tagged["count"] == 2  # both created with the research tag

    def test_validation_422(self, client: TestClient) -> None:
        assert (
            client.post("/api/v1/prompts", json={"name": "", "template": "x"}).status_code
            == 422
        )

    def test_render_preview_uses_real_renderer(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/prompts/test",
            json={"template": "Hello {{who}}!", "variables": {"who": "world"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rendered"] == "Hello world!"
        # scratch template must not leak into the library
        assert client.get("/api/v1/prompts").json()["count"] == 0


class TestEvolutionAPI:
    def test_optimize_without_usage_is_honest(self, client: TestClient) -> None:
        """No usage data → no quality proposals, no invented scores."""
        _create(client)
        data = client.post("/api/v1/prompts/researcher/optimize").json()
        assert "score_improvement" not in data  # the M8 fake is gone
        for proposal in data["proposals"]:
            assert "quality" not in proposal["rationale"].lower()

    def test_usage_recording_and_analysis(self, client: TestClient) -> None:
        _create(client)
        for i in range(6):
            resp = client.post(
                "/api/v1/prompts/researcher/usage",
                json={"output_quality": 0.3, "latency_ms": 120.0, "provider": "anthropic"},
            )
            assert resp.status_code == 200
        analysis = client.get("/api/v1/prompts/researcher/analysis").json()
        assert analysis["usage"]["total_uses"] == 6
        assert analysis["has_sufficient_data"] is True

    def test_low_quality_evidence_produces_proposal(self, client: TestClient) -> None:
        _create(client)
        for _ in range(6):
            client.post(
                "/api/v1/prompts/researcher/usage",
                json={"output_quality": 0.2},
            )
        data = client.post("/api/v1/prompts/researcher/optimize").json()
        quality_props = [
            p for p in data["proposals"] if "quality" in p["rationale"].lower()
        ]
        assert len(quality_props) == 1
        assert quality_props[0]["evidence"]["total_uses"] == 6

    def test_full_evolution_cycle_with_rollback(self, client: TestClient) -> None:
        _create(client, template="Original {{topic}}")
        # external proposal → apply → rollback
        prop = client.post(
            "/api/v1/prompts/researcher/proposals",
            json={"proposed_template": "Improved {{topic}}", "rationale": "better"},
        ).json()
        applied = client.post(
            f"/api/v1/prompts/proposals/{prop['proposal_id']}/apply"
        ).json()
        assert applied["new_version"] == 2
        assert (
            client.get("/api/v1/prompts/researcher").json()["template"]
            == "Improved {{topic}}"
        )

        history = client.get("/api/v1/prompts/researcher/history").json()
        assert history["count"] >= 2

        rollback = client.post(
            "/api/v1/prompts/researcher/rollback", json={"version": 1}
        ).json()
        assert rollback["new_version"] == 3
        assert (
            client.get("/api/v1/prompts/researcher").json()["template"]
            == "Original {{topic}}"
        )

    def test_apply_unknown_proposal_404(self, client: TestClient) -> None:
        assert (
            client.post("/api/v1/prompts/proposals/ghost/apply").status_code == 404
        )

    def test_rollback_unknown_version_404(self, client: TestClient) -> None:
        _create(client)
        resp = client.post(
            "/api/v1/prompts/researcher/rollback", json={"version": 42}
        )
        assert resp.status_code == 404

    def test_usage_validation_422(self, client: TestClient) -> None:
        _create(client)
        resp = client.post(
            "/api/v1/prompts/researcher/usage", json={"output_quality": 1.5}
        )
        assert resp.status_code == 422
