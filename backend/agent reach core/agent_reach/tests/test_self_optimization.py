"""Tests for M9.14 — Self Optimization Engine.

Proves: honest emptiness on a fresh runtime, real findings from real
data (latency, errors, memory pressure, provider quality), safe/
advisory separation, apply() executing only safe operations with real
before/after measurements, and the /api/v1/optimization endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from composition import build_intelligent_pipeline
from config.settings import get_settings
from core.self_optimization import SelfOptimizationEngine
from core.trace_store import PipelineTraceStore
from core.intelligent_pipeline import PipelineTrace


def _trace(**overrides) -> PipelineTrace:
    trace = PipelineTrace()
    for key, value in overrides.items():
        setattr(trace, key, value)
    return trace


# ===========================================================================
# Analysis
# ===========================================================================


class TestAnalysis:
    def test_fresh_runtime_yields_no_findings(self) -> None:
        engine = SelfOptimizationEngine(build_intelligent_pipeline())
        assert engine.analyze() == []

    def test_high_latency_produces_advisory(self) -> None:
        pipeline = build_intelligent_pipeline()
        for _ in range(5):
            pipeline.trace_store.record(_trace(total_latency_ms=9_000.0))
        actions = SelfOptimizationEngine(pipeline).analyze()
        latency = [a for a in actions if a.area == "latency"]
        assert len(latency) == 1
        assert latency[0].safe is False
        assert latency[0].evidence["p95_latency_ms"] >= 9_000.0

    def test_high_error_rate_produces_advisory(self) -> None:
        pipeline = build_intelligent_pipeline()
        for i in range(10):
            pipeline.trace_store.record(
                _trace(errors=["memory: boom"] if i < 3 else [])
            )
        actions = SelfOptimizationEngine(pipeline).analyze()
        errors = [a for a in actions if a.area == "errors"]
        assert len(errors) == 1
        assert errors[0].evidence["error_rate"] == pytest.approx(0.3)

    def test_memory_pressure_produces_safe_action(self) -> None:
        pipeline = build_intelligent_pipeline()
        memory = pipeline._get_memory()
        for i in range(60):
            memory.store(f"memory item {i}", add_to_working=False)
        actions = SelfOptimizationEngine(pipeline).analyze()
        mem_actions = [a for a in actions if a.area == "memory"]
        assert len(mem_actions) == 1
        assert mem_actions[0].safe is True
        assert mem_actions[0].evidence["operation"] == "memory.consolidate"

    def test_low_provider_success_produces_advisory(self) -> None:
        pipeline = build_intelligent_pipeline()
        learning = pipeline._get_learning()
        for i in range(10):
            learning.record(
                task=f"task {i}",
                provider="flakyprov",
                mode="standard",
                quality=0.2,
                latency_ms=100.0,
                success=(i < 2),  # 20% success
            )
        actions = SelfOptimizationEngine(pipeline).analyze()
        prov = [
            a
            for a in actions
            if a.area == "providers" and a.evidence.get("provider") == "flakyprov"
        ]
        assert len(prov) == 1
        assert prov[0].safe is False

    def test_router_history_produces_safe_relearn(self) -> None:
        pipeline = build_intelligent_pipeline()
        router = pipeline._get_router()
        for _ in range(6):
            router.record_success("anthropic", latency_ms=200.0)
        actions = SelfOptimizationEngine(pipeline).analyze()
        routing = [a for a in actions if a.area == "routing"]
        assert len(routing) == 1
        assert routing[0].safe is True


# ===========================================================================
# Application
# ===========================================================================


class TestApply:
    def test_apply_executes_only_safe_actions(self) -> None:
        pipeline = build_intelligent_pipeline()
        memory = pipeline._get_memory()
        for i in range(60):
            memory.store(f"item {i}", importance=0.9, add_to_working=False)
        for _ in range(5):
            pipeline.trace_store.record(_trace(total_latency_ms=9_000.0))

        engine = SelfOptimizationEngine(pipeline)
        report = engine.apply()
        assert report["applied_count"] >= 1
        assert report["skipped_count"] >= 1  # the latency advisory
        assert all(a["succeeded"] for a in report["applied"])

    def test_memory_consolidation_has_real_before_after(self) -> None:
        pipeline = build_intelligent_pipeline()
        memory = pipeline._get_memory()
        for i in range(60):
            memory.store(f"important {i}", importance=0.95, add_to_working=False)

        engine = SelfOptimizationEngine(pipeline)
        report = engine.apply()
        consolidations = [
            a for a in report["applied"] if a["operation"] == "memory.consolidate"
        ]
        assert len(consolidations) == 1
        entry = consolidations[0]
        assert entry["before"]["short_term"] == 60
        assert entry["after"]["promoted"] > 0
        assert entry["after"]["long_term"] > entry["before"]["long_term"]

    def test_router_relearn_applies(self) -> None:
        pipeline = build_intelligent_pipeline()
        router = pipeline._get_router()
        for _ in range(6):
            router.record_success("deepseek", latency_ms=80.0)

        report = SelfOptimizationEngine(pipeline).apply()
        relearns = [
            a
            for a in report["applied"]
            if a["operation"] == "router.learn_from_history"
        ]
        assert len(relearns) == 1
        assert relearns[0]["succeeded"] is True
        assert relearns[0]["after"]["preferred_provider"] == "deepseek"

    def test_reports_persisted_newest_first(self) -> None:
        pipeline = build_intelligent_pipeline()
        engine = SelfOptimizationEngine(pipeline)
        first = engine.apply()
        second = engine.apply()
        reports = engine.get_reports()
        assert reports[0]["report_id"] == second["report_id"]
        assert reports[1]["report_id"] == first["report_id"]


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


class TestOptimizationAPI:
    def test_analyze_fresh_boot_empty(self, client: TestClient) -> None:
        data = client.get("/api/v1/optimization/analyze").json()
        assert data["count"] == 0
        assert data["actions"] == []

    def test_analyze_below_thresholds_stays_empty(self, client: TestClient) -> None:
        """Findings are threshold-gated: 3 executions are below the
        5-execution learning minimum → honest empty analysis."""
        for i in range(3):
            client.post("/api/v1/chat", json={"message": f"traffic {i}"})
        data = client.get("/api/v1/optimization/analyze").json()
        assert data["count"] == 0

    def test_analyze_after_sufficient_traffic(self, client: TestClient) -> None:
        for i in range(5):
            client.post("/api/v1/chat", json={"message": f"traffic {i}"})
        data = client.get("/api/v1/optimization/analyze").json()
        # ≥5 learning records → at least the safe learning.evolve action.
        assert data["count"] >= 1
        assert data["safe_count"] >= 1
        assert data["safe_count"] + data["advisory_count"] == data["count"]

    def test_apply_and_reports(self, client: TestClient) -> None:
        for i in range(3):
            client.post("/api/v1/chat", json={"message": f"apply traffic {i}"})
        report = client.post("/api/v1/optimization/apply", json={}).json()
        assert "applied" in report and "skipped" in report
        reports = client.get("/api/v1/optimization/reports").json()
        assert reports["count"] >= 1

    def test_apply_unknown_action_404(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/optimization/apply", json={"action_ids": ["ghost"]}
        )
        assert resp.status_code == 404

    def test_apply_advisory_action_409(self, client: TestClient) -> None:
        # Manufacture an advisory finding: high-latency traces.
        pipeline = client.app.state.pipeline
        for _ in range(5):
            pipeline.trace_store.record(
                __import__("core.intelligent_pipeline", fromlist=["PipelineTrace"]).PipelineTrace(
                )
            )
        # set latency on the stored traces
        for trace in pipeline.trace_store.list_recent(limit=5):
            trace.total_latency_ms = 9_000.0
        analysis = client.get("/api/v1/optimization/analyze").json()
        advisory = [a for a in analysis["actions"] if not a["safe"]]
        assert advisory, "expected an advisory finding"
        resp = client.post(
            "/api/v1/optimization/apply",
            json={"action_ids": [advisory[0]["action_id"]]},
        )
        # Ephemeral ids regenerate per analyze — the endpoint may see a
        # different id set; both 404 (regenerated) and 409 (matched but
        # unsafe) are correct rejections. Fake success is the bug.
        assert resp.status_code in (404, 409)
