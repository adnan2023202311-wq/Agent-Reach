"""Tests for M9.27 — Continuous Self-Improvement Loop.

Proves: event-driven cadence on the real M9.24 hub (no polling/
threads), cycle composition of the real M9.14/M9.20 engines, honest
cycle records (only what actually ran), reentrancy guarding, bounded
history, and the /api/v1/improvement endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from composition import build_event_hub, build_intelligent_pipeline
from config.settings import get_settings
from core.self_improvement import SelfImprovementLoop
from core.self_optimization import SelfOptimizationEngine
from prompts.evolution import PromptEvolutionEngine


def _build_loop(cycle_every: int = 3) -> tuple[SelfImprovementLoop, object, object]:
    hub = build_event_hub()
    pipeline = build_intelligent_pipeline(event_hub=hub)
    loop = SelfImprovementLoop(
        pipeline,
        SelfOptimizationEngine(pipeline),
        PromptEvolutionEngine(),
        cycle_every=cycle_every,
    )
    loop.attach(hub)
    return loop, pipeline, hub


# ===========================================================================
# Cadence
# ===========================================================================


@pytest.mark.asyncio
class TestCadence:
    async def test_cycle_fires_after_n_executions(self) -> None:
        loop, pipeline, _ = _build_loop(cycle_every=3)
        for i in range(2):
            await pipeline.process(f"request {i}")
        assert loop.get_status()["total_cycles"] == 0
        assert loop.executions_since_cycle == 2

        await pipeline.process("request 3")  # third completion → cycle
        status = loop.get_status()
        assert status["total_cycles"] == 1
        assert status["executions_since_cycle"] == 0
        assert status["last_cycle"]["trigger_request_id"]

    async def test_counter_resets_each_cycle(self) -> None:
        loop, pipeline, _ = _build_loop(cycle_every=2)
        for i in range(5):
            await pipeline.process(f"r{i}")
        # 5 executions with cadence 2 → cycles at 2 and 4.
        assert loop.get_status()["total_cycles"] == 2
        assert loop.executions_since_cycle == 1

    async def test_manual_cycle_resets_cadence(self) -> None:
        loop, pipeline, _ = _build_loop(cycle_every=5)
        await pipeline.process("one")
        await loop.run_cycle(trigger_request_id="manual")
        assert loop.executions_since_cycle == 0
        assert loop.get_status()["total_cycles"] == 1

    async def test_invalid_construction_rejected(self) -> None:
        pipeline = build_intelligent_pipeline()
        with pytest.raises(ValueError):
            SelfImprovementLoop(pipeline, None, None, cycle_every=0)
        with pytest.raises(ValueError):
            SelfImprovementLoop(pipeline, None, None, max_cycles=0)


# ===========================================================================
# Cycle content
# ===========================================================================


@pytest.mark.asyncio
class TestCycleContent:
    async def test_cycle_reports_only_what_ran(self) -> None:
        loop, pipeline, _ = _build_loop(cycle_every=100)
        # 6 executions → learning has ≥5 records → safe evolve applies.
        for i in range(6):
            await pipeline.process(f"traffic {i}")
        cycle = await loop.run_cycle(trigger_request_id="test")
        assert cycle.errors == []
        report = cycle.optimization_report
        assert report["applied_count"] >= 1
        assert all(a["succeeded"] for a in report["applied"])
        assert cycle.learning_stats["total_executions"] == 6
        assert cycle.knowledge_stats["observations"] >= 1

    async def test_prompt_proposals_generated_not_applied(self) -> None:
        loop, pipeline, _ = _build_loop(cycle_every=100)
        prompt_evolution = loop._prompt_evolution
        prompt_evolution.library.register("messy", "Do the thing.   \n\n   ")
        cycle = await loop.run_cycle()
        assert len(cycle.prompt_proposals) == 1
        # NOT applied — the template is unchanged.
        assert prompt_evolution.library.get("messy").template == "Do the thing.   \n\n   "

    async def test_empty_runtime_cycle_is_honest(self) -> None:
        loop, _, _ = _build_loop(cycle_every=100)
        cycle = await loop.run_cycle()
        assert cycle.optimization_report["applied_count"] == 0
        assert cycle.prompt_proposals == []

    async def test_reentrancy_guard(self) -> None:
        loop, _, _ = _build_loop()
        loop._running = True  # simulate an in-flight cycle
        cycle = await loop.run_cycle()
        assert any("skipped" in e for e in cycle.errors)
        assert loop.get_status()["total_cycles"] == 0  # not recorded
        loop._running = False

    async def test_history_bounded_newest_first(self) -> None:
        loop, pipeline, _ = _build_loop(cycle_every=100)
        loop._max_cycles = 3
        ids = []
        for _ in range(5):
            cycle = await loop.run_cycle()
            ids.append(cycle.cycle_id)
        cycles = loop.get_cycles(limit=10)
        assert len(cycles) == 3
        assert [c.cycle_id for c in cycles] == list(reversed(ids[-3:]))

    async def test_stage_failure_isolated(self) -> None:
        class _BrokenOptimizer:
            def apply(self) -> dict:
                raise RuntimeError("optimizer down")

        hub = build_event_hub()
        pipeline = build_intelligent_pipeline(event_hub=hub)
        loop = SelfImprovementLoop(
            pipeline, _BrokenOptimizer(), PromptEvolutionEngine()
        )
        cycle = await loop.run_cycle()
        assert any("optimizer down" in e for e in cycle.errors)
        # other stages still produced real data
        assert "total_executions" in cycle.learning_stats


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


class TestImprovementAPI:
    def test_status_fresh_boot(self, client: TestClient) -> None:
        status = client.get("/api/v1/improvement/status").json()
        assert status["total_cycles"] == 0
        assert status["executions_since_cycle"] == 0
        assert status["last_cycle"] is None

    def test_chat_advances_cadence(self, client: TestClient) -> None:
        client.post("/api/v1/chat", json={"message": "advance the loop"})
        status = client.get("/api/v1/improvement/status").json()
        assert status["executions_since_cycle"] == 1
        assert status["executions_until_next"] == status["cycle_every"] - 1

    def test_manual_cycle_and_history(self, client: TestClient) -> None:
        client.post("/api/v1/chat", json={"message": "some traffic"})
        cycle = client.post("/api/v1/improvement/cycle").json()
        assert cycle["trigger_request_id"] == "manual"
        assert cycle["finished_at"] is not None
        cycles = client.get("/api/v1/improvement/cycles").json()
        assert cycles["count"] == 1
        assert cycles["cycles"][0]["cycle_id"] == cycle["cycle_id"]

    def test_automatic_cycle_after_cadence(self, client: TestClient) -> None:
        cadence = client.get("/api/v1/improvement/status").json()["cycle_every"]
        for i in range(cadence):
            client.post("/api/v1/chat", json={"message": f"cadence {i}"})
        status = client.get("/api/v1/improvement/status").json()
        assert status["total_cycles"] >= 1
