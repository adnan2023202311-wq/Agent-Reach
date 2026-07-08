"""Tests for M9.9 — Runtime Agent Studio.

Covers the AgentStudio runtime (save/version/publish/run/observe) and
the /api/v1/studio/agents endpoints. Runs execute through the real
IntelligentPipeline (MockModelClient backend in tests) and must carry
the request_id of a persisted pipeline trace — proving the
Create → Configure → Save → Run → Observe → Debug → Improve loop is
live, not mocked.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agents.studio import AgentStudio
from api.main import create_app
from composition import build_intelligent_pipeline
from config.settings import get_settings


# ===========================================================================
# Engine: definitions & versioning
# ===========================================================================


class TestStudioDefinitions:
    def _studio(self) -> AgentStudio:
        return AgentStudio(build_intelligent_pipeline())

    def test_save_creates_definition(self) -> None:
        studio = self._studio()
        definition = studio.save(
            "Research Helper", system_prompt="You research things."
        )
        assert definition.agent_id == "research_helper"
        assert definition.version == 1
        assert not definition.published

    def test_save_same_id_bumps_version_and_records_history(self) -> None:
        studio = self._studio()
        studio.save("Helper", system_prompt="v1 prompt")
        updated = studio.save("Helper", system_prompt="v2 prompt")
        assert updated.version == 2
        versions = studio.get_versions("helper")
        assert len(versions) == 1
        assert versions[0]["system_prompt"] == "v1 prompt"

    def test_empty_name_rejected(self) -> None:
        studio = self._studio()
        with pytest.raises(ValueError):
            studio.save("   ")

    def test_out_of_range_temperature_rejected(self) -> None:
        studio = self._studio()
        with pytest.raises(ValueError):
            studio.save("Hot Agent", temperature=3.0)

    def test_invalid_max_tokens_rejected(self) -> None:
        studio = self._studio()
        with pytest.raises(ValueError):
            studio.save("Tiny Agent", max_tokens=0)

    def test_publish_and_unpublish(self) -> None:
        studio = self._studio()
        studio.save("Publishable")
        assert studio.publish("publishable").published is True
        assert studio.unpublish("publishable").published is False

    def test_publish_unknown_raises(self) -> None:
        studio = self._studio()
        with pytest.raises(KeyError):
            studio.publish("ghost")

    def test_delete_removes_everything(self) -> None:
        studio = self._studio()
        studio.save("Doomed", system_prompt="v1")
        studio.save("Doomed", system_prompt="v2")
        assert studio.delete("doomed") is True
        assert studio.get("doomed") is None
        assert studio.get_versions("doomed") == []
        assert studio.delete("doomed") is False

    def test_list_agents_with_published_filter(self) -> None:
        studio = self._studio()
        studio.save("Draft One")
        studio.save("Live One")
        studio.publish("live_one")
        assert len(studio.list_agents()) == 2
        published = studio.list_agents(published_only=True)
        assert [a.agent_id for a in published] == ["live_one"]


# ===========================================================================
# Engine: run / observe
# ===========================================================================


@pytest.mark.asyncio
class TestStudioRuns:
    def _studio(self) -> AgentStudio:
        return AgentStudio(build_intelligent_pipeline())

    async def test_run_executes_through_real_pipeline(self) -> None:
        studio = self._studio()
        studio.save("Runner", system_prompt="Answer concisely.")
        record = await studio.run("runner", "What is Agent Reach?")
        assert record.status == "succeeded"
        assert record.answer
        assert record.latency_ms > 0

    async def test_run_links_to_persisted_trace(self) -> None:
        """The record's request_id must resolve in the pipeline's
        trace store — this is what makes Observe/Debug real."""
        pipeline = build_intelligent_pipeline()
        studio = AgentStudio(pipeline)
        studio.save("Traceable")
        record = await studio.run("traceable", "Trace this run")
        assert record.request_id
        assert pipeline.get_trace(record.request_id) is not None

    async def test_run_unknown_agent_raises(self) -> None:
        studio = self._studio()
        with pytest.raises(KeyError):
            await studio.run("ghost", "hello")

    async def test_empty_prompt_rejected(self) -> None:
        studio = self._studio()
        studio.save("Strict")
        with pytest.raises(ValueError):
            await studio.run("strict", "   ")

    async def test_history_and_metrics_reflect_real_runs(self) -> None:
        studio = self._studio()
        studio.save("Tracked")
        await studio.run("tracked", "first")
        await studio.run("tracked", "second")
        history = studio.get_history("tracked")
        assert len(history) == 2
        assert history[0].prompt == "second"  # newest first
        metrics = studio.get_metrics("tracked")
        assert metrics["total_runs"] == 2
        assert metrics["success_rate"] == 1.0
        assert metrics["avg_latency_ms"] > 0

    async def test_metrics_empty_agent_honest_zeros(self) -> None:
        studio = self._studio()
        studio.save("Unused")
        metrics = studio.get_metrics("unused")
        assert metrics["total_runs"] == 0
        assert metrics["success_rate"] == 0.0

    async def test_run_records_agent_version(self) -> None:
        studio = self._studio()
        studio.save("Versioned", system_prompt="v1")
        r1 = await studio.run("versioned", "with v1")
        studio.save("Versioned", system_prompt="v2")
        r2 = await studio.run("versioned", "with v2")
        assert r1.agent_version == 1
        assert r2.agent_version == 2


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


def _draft(client: TestClient, name: str, **extra) -> str:
    resp = client.post(
        "/api/v1/studio/agents/draft",
        json={"name": name, "system_prompt": "You are helpful.", **extra},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


class TestStudioAPI:
    def test_draft_create_and_versioning(self, client: TestClient) -> None:
        agent_id = _draft(client, "API Agent")
        assert agent_id == "api_agent"
        second = client.post(
            "/api/v1/studio/agents/draft",
            json={"name": "API Agent", "system_prompt": "updated"},
        )
        assert second.json()["version"] == 2

    def test_invalid_temperature_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/studio/agents/draft",
            json={"name": "Bad", "temperature": 9.9},
        )
        assert resp.status_code == 422

    def test_test_endpoint_runs_real_pipeline(self, client: TestClient) -> None:
        agent_id = _draft(client, "Live Tester")
        resp = client.post(
            f"/api/v1/studio/agents/{agent_id}/test",
            json={"prompt": "Run through the pipeline"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "succeeded"
        assert data["request_id"]
        # Observe/Debug: the trace is retrievable from the observatory.
        trace = client.get(f"/api/v1/observatory/trace/{data['request_id']}")
        assert trace.status_code == 200
        assert trace.json()["found"] is True

    def test_test_unknown_agent_404(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/studio/agents/ghost/test", json={"prompt": "hi"}
        )
        assert resp.status_code == 404

    def test_publish_unknown_agent_404_no_fake_success(self, client: TestClient) -> None:
        """The M8 mock returned success for unknown agents. M9.9 must 404."""
        assert client.post("/api/v1/studio/agents/ghost/publish").status_code == 404

    def test_publish_then_listed_as_published(self, client: TestClient) -> None:
        agent_id = _draft(client, "Publisher")
        client.post(f"/api/v1/studio/agents/{agent_id}/publish")
        listing = client.get("/api/v1/studio/agents").json()
        assert any(a["id"] == agent_id for a in listing["published"])
        assert not any(a["id"] == agent_id for a in listing["drafts"])

    def test_detail_with_metrics_and_runs(self, client: TestClient) -> None:
        agent_id = _draft(client, "Detailed")
        client.post(
            f"/api/v1/studio/agents/{agent_id}/test", json={"prompt": "once"}
        )
        detail = client.get(f"/api/v1/studio/agents/{agent_id}").json()
        assert detail["metrics"]["total_runs"] == 1
        assert len(detail["recent_runs"]) == 1

    def test_versions_endpoint(self, client: TestClient) -> None:
        agent_id = _draft(client, "Evolver")
        client.post(
            "/api/v1/studio/agents/draft",
            json={"name": "Evolver", "system_prompt": "improved"},
        )
        versions = client.get(f"/api/v1/studio/agents/{agent_id}/versions").json()
        assert versions["versions"] == 2
        assert len(versions["history"]) == 1

    def test_runs_endpoint(self, client: TestClient) -> None:
        agent_id = _draft(client, "Historied")
        client.post(f"/api/v1/studio/agents/{agent_id}/test", json={"prompt": "a"})
        client.post(f"/api/v1/studio/agents/{agent_id}/test", json={"prompt": "b"})
        runs = client.get(f"/api/v1/studio/agents/{agent_id}/runs").json()
        assert runs["count"] == 2
        assert runs["metrics"]["total_runs"] == 2

    def test_delete_agent(self, client: TestClient) -> None:
        agent_id = _draft(client, "Removable")
        assert client.delete(f"/api/v1/studio/agents/{agent_id}").status_code == 200
        assert client.get(f"/api/v1/studio/agents/{agent_id}").status_code == 404

    def test_catalog_still_lists_native_agents(self, client: TestClient) -> None:
        """Backward compatibility: native agents stay in the catalog."""
        listing = client.get("/api/v1/studio/agents").json()
        assert len(listing["catalog"]) >= 1
        assert all(a["source"] == "native" for a in listing["catalog"])
