"""Tests for M9.25/M9.30 — Autonomous Release Pipeline & Validation V2.

Proves: every validation runs against real machinery (live smoke,
regressions, static security over the actual api/+core sources,
bounded load probe with real latencies, backend surface via the live
route table, documentation files on disk), the absolute publication
gate (a failing validation REFUSES the release with a real refusal
record), monotonic semantic versioning, packaging manifests, and the
/api/v1/release endpoints.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from composition import build_intelligent_pipeline, build_tool_runtime
from config.settings import get_settings
from core.code_review import CodeReviewEngine
from core.platform_introspection import PlatformIntrospection
from core.qa_framework import QAFramework
from core.release_pipeline import PerformanceBudget, ReleasePipeline


def _release_pipeline(**overrides) -> ReleasePipeline:
    pipeline = build_intelligent_pipeline()
    tool_runtime = build_tool_runtime()
    introspection = PlatformIntrospection(pipeline, tool_runtime)
    qa = QAFramework(pipeline, tool_runtime, introspection=introspection)
    return ReleasePipeline(
        pipeline,
        introspection,
        qa,
        CodeReviewEngine(),
        budget=overrides.pop("budget", PerformanceBudget(load_requests=2)),
        **overrides,
    )


# ===========================================================================
# Validations
# ===========================================================================


@pytest.mark.asyncio
class TestValidations:
    async def test_all_validations_pass_on_healthy_platform(self) -> None:
        release = _release_pipeline()
        checks = await release.validate_all()
        by_name = {c["validation"]: c for c in checks}
        assert set(by_name) == {
            "runtime", "regression", "security", "load", "performance",
            "backend_surface", "documentation", "unit_and_integration_tests",
        }
        # backend_surface honestly fails without an app attached —
        # everything else passes on the healthy platform.
        for name, check in by_name.items():
            if name == "backend_surface":
                assert check["passed"] is False
            else:
                assert check["passed"] is True, name

    async def test_security_scans_real_sources(self) -> None:
        release = _release_pipeline()
        checks = await release.validate_all()
        security = next(c for c in checks if c["validation"] == "security")
        # our own api/ + core/ trees were genuinely scanned
        assert security["detail"]["files_scanned"] > 30
        assert security["detail"]["critical_findings"] == []

    async def test_load_probe_measures_real_latency(self) -> None:
        release = _release_pipeline()
        checks = await release.validate_all()
        load = next(c for c in checks if c["validation"] == "load")
        assert load["detail"]["concurrent_requests"] == 2
        assert load["detail"]["failures"] == 0
        assert load["detail"]["avg_latency_ms"] > 0

    async def test_performance_budget_gates(self) -> None:
        release = _release_pipeline(
            budget=PerformanceBudget(load_requests=2, max_error_rate=0.0)
        )
        # Poison the trace store with an errored trace → error_rate > 0.
        from core.intelligent_pipeline import PipelineTrace

        trace = PipelineTrace()
        trace.errors = ["memory: boom"]
        release._pipeline.trace_store.record(trace)
        checks = await release.validate_all()
        performance = next(c for c in checks if c["validation"] == "performance")
        assert performance["passed"] is False

    async def test_documentation_check_missing_files_fails(self, tmp_path: Path) -> None:
        release = _release_pipeline(repo_root=tmp_path)  # empty dir
        checks = await release.validate_all()
        docs = next(c for c in checks if c["validation"] == "documentation")
        assert docs["passed"] is False


# ===========================================================================
# Publication gate
# ===========================================================================


@pytest.mark.asyncio
class TestPublicationGate:
    async def test_failing_validation_refuses_release(self) -> None:
        release = _release_pipeline()  # backend_surface fails (no app)
        record = await release.publish()
        assert record.passed is False
        assert record.published is False
        assert record.version == ""
        assert "REFUSED" in record.notes
        assert "backend_surface" in record.notes
        # the refusal is itself a stored record
        assert release.get_release(record.release_id) is record

    async def test_invalid_bump_rejected(self) -> None:
        release = _release_pipeline()
        with pytest.raises(ValueError):
            await release.publish(bump="cosmic")

    async def test_version_monotonic_per_pipeline_instance(self) -> None:
        release = _release_pipeline()
        assert release._next_version("minor") == "0.1.0"
        assert release._next_version("patch") == "0.1.1"
        assert release._next_version("major") == "1.0.0"
        assert release._next_version("minor") == "1.1.0"


# ===========================================================================
# API (app attached → backend surface check can pass)
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


class TestReleaseAPI:
    def test_validate_endpoint_full_pass_with_live_app(self, client: TestClient) -> None:
        result = client.post("/api/v1/release/validate").json()
        by_name = {c["validation"]: c for c in result["checks"]}
        assert by_name["backend_surface"]["passed"] is True
        assert result["passed"] is True

    def test_publish_produces_versioned_manifest(self, client: TestClient) -> None:
        record = client.post(
            "/api/v1/release/publish", json={"bump": "minor", "notes": "first"}
        ).json()
        assert record["published"] is True
        assert record["version"] == "0.1.0"
        manifest = record["manifest"]
        assert manifest["version"] == "0.1.0"
        assert "core" in manifest["packages"]
        assert "runtime" in manifest["validations_passed"]

        second = client.post(
            "/api/v1/release/publish", json={"bump": "patch"}
        ).json()
        assert second["version"] == "0.1.1"

    def test_release_history(self, client: TestClient) -> None:
        created = client.post("/api/v1/release/publish", json={}).json()
        listing = client.get("/api/v1/release/releases").json()
        assert listing["count"] >= 1
        detail = client.get(f"/api/v1/release/releases/{created['release_id']}")
        assert detail.status_code == 200
        assert client.get("/api/v1/release/releases/ghost").status_code == 404

    def test_invalid_bump_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/release/publish", json={"bump": "cosmic"})
        assert resp.status_code == 422
