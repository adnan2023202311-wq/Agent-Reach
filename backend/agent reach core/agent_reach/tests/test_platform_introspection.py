"""Tests for M9.11 — Self-Developing Platform (introspection).

Proves: real module/route/subsystem/tool/runtime inspection, honest
empty findings on a healthy idle platform, evidence-based bottleneck
detection from real trace data, live smoke validation executing a
genuine pipeline request, and the /api/v1/platform endpoints
including improve()'s delegation to the single M9.14 apply path.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from composition import build_intelligent_pipeline, build_tool_runtime
from config.settings import get_settings
from core.intelligent_pipeline import PipelineTrace
from core.platform_introspection import PlatformIntrospection


def _trace(**overrides) -> PipelineTrace:
    trace = PipelineTrace()
    for key, value in overrides.items():
        setattr(trace, key, value)
    return trace


# ===========================================================================
# Inspection
# ===========================================================================


class TestInspect:
    def test_modules_from_disk(self) -> None:
        engine = PlatformIntrospection(build_intelligent_pipeline())
        modules = engine.inspect()["modules"]
        packages = modules["packages"]
        # real packages that exist on disk
        for expected in ("core", "memory", "knowledge", "workflows", "api"):
            assert expected in packages
            assert packages[expected] > 0

    def test_subsystems_via_verify_integration(self) -> None:
        engine = PlatformIntrospection(build_intelligent_pipeline())
        subsystems = engine.inspect()["subsystems"]
        assert subsystems["active_count"] >= 8

    def test_tools_and_runtime_sections(self) -> None:
        pipeline = build_intelligent_pipeline()
        engine = PlatformIntrospection(pipeline, build_tool_runtime())
        report = engine.inspect()
        assert report["tools"]["available"] is True
        assert report["tools"]["registry"]["total"] >= 7
        assert report["runtime"]["total_traces"] == 0  # honest zero

    def test_routes_without_app(self) -> None:
        engine = PlatformIntrospection(build_intelligent_pipeline())
        assert engine.inspect()["routes"]["available"] is False


# ===========================================================================
# Analysis
# ===========================================================================


class TestAnalyze:
    def test_healthy_idle_platform_no_findings(self) -> None:
        engine = PlatformIntrospection(build_intelligent_pipeline())
        assert engine.analyze() == []

    def test_persistent_stage_errors_detected(self) -> None:
        pipeline = build_intelligent_pipeline()
        for i in range(10):
            pipeline.trace_store.record(
                _trace(errors=["memory: boom"] if i < 4 else [])
            )
        findings = PlatformIntrospection(pipeline).analyze()
        stage_findings = [
            f for f in findings if f.evidence.get("stage") == "memory"
            and f.area == "runtime"
        ]
        assert len(stage_findings) == 1
        assert stage_findings[0].evidence["error_rate"] == pytest.approx(0.4)

    def test_dominant_stage_latency_detected(self) -> None:
        pipeline = build_intelligent_pipeline()
        for _ in range(6):
            pipeline.trace_store.record(
                _trace(
                    memory_latency_ms=900.0,
                    router_latency_ms=10.0,
                    context_latency_ms=10.0,
                )
            )
        findings = PlatformIntrospection(pipeline).analyze()
        dominant = [
            f for f in findings
            if "dominates" in f.recommendation or f.evidence.get("share", 0) > 0.5
        ]
        assert len(dominant) == 1
        assert dominant[0].evidence["stage"] == "memory"

    def test_latency_analysis_needs_evidence(self) -> None:
        """Fewer than 5 traces → no latency findings (not enough data)."""
        pipeline = build_intelligent_pipeline()
        for _ in range(3):
            pipeline.trace_store.record(_trace(memory_latency_ms=900.0))
        findings = PlatformIntrospection(pipeline).analyze()
        assert all(f.evidence.get("share") is None for f in findings)

    @pytest.mark.asyncio
    async def test_failing_tool_detected(self) -> None:
        pipeline = build_intelligent_pipeline()
        tool_runtime = build_tool_runtime()

        async def broken() -> None:
            raise RuntimeError("nope")

        tool_runtime.registry.register("breaks", broken)
        for _ in range(5):
            await tool_runtime.execute("breaks")

        findings = PlatformIntrospection(pipeline, tool_runtime).analyze()
        tool_findings = [f for f in findings if f.area == "tools"]
        assert len(tool_findings) == 1
        assert tool_findings[0].evidence["tool"] == "breaks"


# ===========================================================================
# Validation
# ===========================================================================


@pytest.mark.asyncio
class TestValidate:
    async def test_smoke_validation_runs_real_request(self) -> None:
        pipeline = build_intelligent_pipeline()
        engine = PlatformIntrospection(pipeline, build_tool_runtime())
        result = await engine.validate()
        assert result["passed"] is True
        checks = {c["check"]: c for c in result["checks"]}
        assert checks["subsystems_constructible"]["passed"] is True
        pipeline_check = checks["pipeline_executes"]
        assert pipeline_check["passed"] is True
        # a REAL trace was produced and persisted
        assert pipeline.get_trace(
            pipeline_check["detail"]["request_id"]
        ) is not None
        assert checks["tool_registry_populated"]["passed"] is True
        assert "CI" in result["note"]


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


class TestPlatformAPI:
    def test_inspect_includes_live_route_table(self, client: TestClient) -> None:
        report = client.get("/api/v1/platform/inspect").json()
        assert report["routes"]["available"] is True
        assert "/api/v1/chat" in report["routes"]["paths"]
        assert "/api/v1/platform/inspect" in report["routes"]["paths"]

    def test_analyze_endpoint(self, client: TestClient) -> None:
        data = client.get("/api/v1/platform/analyze").json()
        assert data["count"] == len(data["findings"])
        assert set(data["by_severity"]) == {"critical", "warning", "info"}

    def test_validate_endpoint(self, client: TestClient) -> None:
        result = client.post("/api/v1/platform/validate").json()
        assert result["passed"] is True

    def test_improve_measures_around_m914_apply(self, client: TestClient) -> None:
        client.post("/api/v1/chat", json={"message": "some traffic first"})
        report = client.post("/api/v1/platform/improve").json()
        assert "optimization_report" in report
        assert "applied_count" in report["optimization_report"]
        assert report["before"]["runtime"]["total_traces"] >= 1
        # after includes the smoke-free measurement (no extra request)
        assert report["after"]["runtime"]["total_traces"] >= 1
