"""Tests for M9.19 — Autonomous Benchmark Laboratory.

Proves: verifiable-task scoring (quality = fraction of deterministic
checks passed), honest skipping of unconfigured providers (no routing
poisoning), routing integration through the router's OWN benchmark
cache and stats (scoring + learn_from_history reflect lab results),
per-category scores, cost estimation from the router cost model, and
the /api/v1/benchmark-lab endpoints.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from benchmarks.provider_lab import (
    BenchmarkTask,
    ProviderBenchmarkLab,
    default_task_suite,
)
from config.settings import Settings, get_settings
from routing.router import ReachIntelligenceRouter


class _ScriptedClient:
    """ModelClient double answering by prompt keyword."""

    def __init__(self, answers: dict[str, str], delay: float = 0.0) -> None:
        self.answers = answers
        self.delay = delay

    async def complete(self, messages, *, system=None, max_tokens=1024) -> str:
        if self.delay:
            await asyncio.sleep(self.delay)
        prompt = messages[0]["content"].lower()
        for keyword, answer in self.answers.items():
            if keyword in prompt:
                return answer
        return "no idea"


_PERFECT_ANSWERS = {
    "speed in": "80",
    "bloops": "yes",
    "reverse_words": "def reverse_words(s):\n    return ' '.join(s.split()[::-1])",
    "tool call": '{"tool": "search", "arguments": {"query": "agent runtimes"}}',
    "access code": "BLUE-MARBLE-47",
}


def _settings(**keys) -> Settings:
    return Settings(default_model_provider="anthropic", **keys)


def _lab(router: Optional[ReachIntelligenceRouter] = None, **kwargs) -> ProviderBenchmarkLab:
    return ProviderBenchmarkLab(
        kwargs.pop("settings", _settings(anthropic_api_key="k")),
        router or ReachIntelligenceRouter(),
        **kwargs,
    )


# ===========================================================================
# Scoring
# ===========================================================================


@pytest.mark.asyncio
class TestScoring:
    async def test_perfect_provider_scores_full_quality(self) -> None:
        lab = _lab(client_factory=lambda name: _ScriptedClient(_PERFECT_ANSWERS))
        run = await lab.run(["anthropic"])
        report = run.reports[0]
        assert report.configured is True
        assert report.quality == 1.0
        assert all(v == 1.0 for v in report.per_category.values())
        assert report.avg_latency_ms >= 0
        assert len(report.task_results) == len(default_task_suite())

    async def test_partial_provider_scores_fraction(self) -> None:
        # Only the arithmetic answer is correct → 1 of 5 checks pass.
        lab = _lab(client_factory=lambda name: _ScriptedClient({"speed in": "80"}))
        run = await lab.run(["anthropic"])
        report = run.reports[0]
        assert report.quality == pytest.approx(1 / 5)
        assert report.per_category["reasoning"] == pytest.approx(1 / 2)
        assert report.per_category["coding"] == 0.0

    async def test_unconfigured_provider_not_benchmarked(self) -> None:
        lab = ProviderBenchmarkLab(_settings(), ReachIntelligenceRouter())
        run = await lab.run(["anthropic"])
        report = run.reports[0]
        assert report.configured is False
        assert "not configured" in report.error
        assert report.task_results == []

    async def test_provider_error_isolated_per_task(self) -> None:
        class _Exploding:
            async def complete(self, *a: Any, **k: Any) -> str:
                raise RuntimeError("api down")

        lab = _lab(client_factory=lambda name: _Exploding())
        run = await lab.run(["anthropic"])
        report = run.reports[0]
        assert report.quality == 0.0
        assert all("api down" in r["error"] for r in report.task_results)

    async def test_cost_estimated_from_router_model(self) -> None:
        lab = _lab(client_factory=lambda name: _ScriptedClient(_PERFECT_ANSWERS))
        run = await lab.run(["anthropic"])
        assert run.reports[0].cost_estimate_usd > 0

    async def test_empty_providers_rejected(self) -> None:
        lab = _lab()
        with pytest.raises(ValueError):
            await lab.run([])

    async def test_custom_task_suite(self) -> None:
        tasks = [
            BenchmarkTask(
                task_id="custom",
                category="reasoning",
                prompt="Say the word banana.",
                checker=lambda out: "banana" in out.lower(),
            )
        ]
        lab = _lab(
            tasks=tasks,
            client_factory=lambda name: _ScriptedClient({"banana": "Banana!"}),
        )
        run = await lab.run(["anthropic"])
        assert run.reports[0].quality == 1.0


# ===========================================================================
# Routing integration
# ===========================================================================


@pytest.mark.asyncio
class TestRoutingIntegration:
    async def test_results_land_in_router_benchmark_cache(self) -> None:
        router = ReachIntelligenceRouter()
        lab = _lab(
            router=router,
            client_factory=lambda name: _ScriptedClient(_PERFECT_ANSWERS),
        )
        await lab.run(["anthropic"])
        assert router.get_benchmark("anthropic", "quality") == 1.0
        assert router.get_benchmark("anthropic", "quality_reasoning") == 1.0
        assert router.get_benchmark("anthropic", "avg_latency_ms") is not None

    async def test_stats_recorded_and_preference_learned(self) -> None:
        router = ReachIntelligenceRouter()
        lab = _lab(
            router=router,
            client_factory=lambda name: _ScriptedClient(_PERFECT_ANSWERS),
        )
        run = await lab.run(["anthropic"])
        stats = router.get_stats("anthropic")
        assert stats.total_calls == len(default_task_suite())
        # 5 successful calls ≥ learn_from_history's minimum → preference set.
        assert router.preferred_provider == "anthropic"
        assert any(
            u["type"] == "preferred_provider" for u in run.routing_updates
        )

    async def test_unconfigured_provider_never_touches_router(self) -> None:
        router = ReachIntelligenceRouter()
        lab = ProviderBenchmarkLab(_settings(), router)
        await lab.run(["anthropic"])
        assert router.get_benchmark("anthropic", "quality") is None
        assert router.get_stats("anthropic").total_calls == 0

    async def test_google_normalized_to_gemini_in_router(self) -> None:
        router = ReachIntelligenceRouter()
        lab = ProviderBenchmarkLab(
            _settings(google_api_key="k"),
            router,
            client_factory=lambda name: _ScriptedClient(_PERFECT_ANSWERS),
        )
        await lab.run(["google"])
        assert router.get_benchmark("gemini", "quality") == 1.0

    async def test_run_history(self) -> None:
        lab = _lab(client_factory=lambda name: _ScriptedClient(_PERFECT_ANSWERS))
        r1 = await lab.run(["anthropic"])
        r2 = await lab.run(["anthropic"])
        runs = lab.get_runs()
        assert [r.run_id for r in runs] == [r2.run_id, r1.run_id]
        assert lab.get_run(r1.run_id) is r1
        assert lab.get_run("ghost") is None


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


class TestBenchmarkLabAPI:
    def test_tasks_listing(self, client: TestClient) -> None:
        data = client.get("/api/v1/benchmark-lab/tasks").json()
        assert data["count"] == len(default_task_suite())
        categories = {t["category"] for t in data["tasks"]}
        assert {"reasoning", "coding", "tool_use", "long_context"} <= categories

    def test_run_with_unconfigured_providers_is_honest(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/benchmark-lab/run", json={"providers": ["anthropic"]}
        )
        assert resp.status_code == 200
        run = resp.json()
        assert run["reports"][0]["configured"] is False
        assert run["routing_updates"] == [] or all(
            u["type"] == "preferred_provider" for u in run["routing_updates"]
        )

    def test_run_validation_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/benchmark-lab/run", json={"providers": []})
        assert resp.status_code == 422

    def test_runs_history_endpoints(self, client: TestClient) -> None:
        run = client.post(
            "/api/v1/benchmark-lab/run", json={"providers": ["anthropic"]}
        ).json()
        listing = client.get("/api/v1/benchmark-lab/runs").json()
        assert listing["count"] >= 1
        detail = client.get(f"/api/v1/benchmark-lab/runs/{run['run_id']}")
        assert detail.status_code == 200
        assert client.get("/api/v1/benchmark-lab/runs/ghost").status_code == 404
