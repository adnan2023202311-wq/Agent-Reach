"""Tests for M9.13 — Autonomous QA Framework.

Proves: discovery from REAL failure signals only (clean runtime → no
bugs), fingerprint deduplication across discovery runs, root-cause
stage attribution from structured trace errors, reproduction through
the shared runtime with honest NOT_REPRODUCIBLE outcomes, regression
case execution, full QA reports, and the /api/v1/qa endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from composition import build_intelligent_pipeline, build_tool_runtime
from config.settings import get_settings
from core.intelligent_pipeline import PipelineTrace
from core.qa_framework import QAFramework


def _errored_trace(request_id: str = "", errors: list[str] | None = None) -> PipelineTrace:
    trace = PipelineTrace()
    if request_id:
        trace.request_id = request_id
    trace.errors = errors if errors is not None else ["memory: boom"]
    trace.final_answer = "original failing request text"
    return trace


# ===========================================================================
# Discovery
# ===========================================================================


class TestDiscovery:
    def test_clean_runtime_discovers_nothing(self) -> None:
        qa = QAFramework(build_intelligent_pipeline())
        assert qa.discover() == []

    def test_pipeline_errors_become_bugs_with_root_cause(self) -> None:
        pipeline = build_intelligent_pipeline()
        pipeline.trace_store.record(
            _errored_trace(errors=["memory: index broken", "context: overflow"])
        )
        qa = QAFramework(pipeline)
        bugs = qa.discover()
        assert len(bugs) == 1
        bug = bugs[0]
        assert bug.source == "pipeline"
        assert bug.root_cause["stages"] == ["context", "memory"]
        assert bug.root_cause["detail"]["memory"] == ["index broken"]
        # a regression case was stored
        assert len(qa.list_regression_cases()) == 1

    def test_discovery_deduplicates_across_runs(self) -> None:
        pipeline = build_intelligent_pipeline()
        pipeline.trace_store.record(_errored_trace())
        qa = QAFramework(pipeline)
        first = qa.discover()
        second = qa.discover()
        assert len(first) == 1
        assert second == []

    @pytest.mark.asyncio
    async def test_failed_tool_executions_become_bugs(self) -> None:
        pipeline = build_intelligent_pipeline()
        tool_runtime = build_tool_runtime()
        await tool_runtime.execute("nonexistent_tool")
        qa = QAFramework(pipeline, tool_runtime)
        bugs = qa.discover()
        tool_bugs = [b for b in bugs if b.source == "tool"]
        assert len(tool_bugs) == 1
        assert tool_bugs[0].evidence["tool_name"] == "nonexistent_tool"
        assert tool_bugs[0].root_cause["error"]

    def test_successful_traces_never_become_bugs(self) -> None:
        pipeline = build_intelligent_pipeline()
        clean = PipelineTrace()
        pipeline.trace_store.record(clean)
        qa = QAFramework(pipeline)
        assert qa.discover() == []


# ===========================================================================
# Reproduction & regressions
# ===========================================================================


@pytest.mark.asyncio
class TestReproduction:
    async def test_not_reproducible_when_rerun_succeeds(self) -> None:
        """MockModelClient runs cleanly, so re-running the request
        yields no stage errors → honest NOT_REPRODUCIBLE."""
        pipeline = build_intelligent_pipeline()
        pipeline.trace_store.record(_errored_trace(request_id="orig-1"))
        qa = QAFramework(pipeline)
        bug = qa.discover()[0]

        result = await qa.reproduce(bug.bug_id)
        assert result.status == "not_reproducible"
        repro = result.reproduction
        assert repro["reproduced"] is False
        assert repro["original_request_id"] == "orig-1"
        # the reproduction run is a REAL persisted trace
        assert pipeline.get_trace(repro["reproduction_request_id"]) is not None

    async def test_tool_bug_reproduces_when_still_failing(self) -> None:
        pipeline = build_intelligent_pipeline()
        tool_runtime = build_tool_runtime()
        await tool_runtime.execute("nonexistent_tool")
        qa = QAFramework(pipeline, tool_runtime)
        bug = qa.discover()[0]

        result = await qa.reproduce(bug.bug_id)
        assert result.status == "reproduced"
        assert result.reproduction["reproduced"] is True

    async def test_reproduce_unknown_bug_raises(self) -> None:
        qa = QAFramework(build_intelligent_pipeline())
        with pytest.raises(KeyError):
            await qa.reproduce("ghost")

    async def test_regression_run_reports_per_case(self) -> None:
        pipeline = build_intelligent_pipeline()
        pipeline.trace_store.record(_errored_trace())
        qa = QAFramework(pipeline)
        qa.discover()

        report = await qa.run_regressions()
        assert report["total"] == 1
        # clean rerun → the regression passes
        assert report["passed"] == 1
        assert report["results"][0]["request_id"]

    async def test_full_qa_report(self) -> None:
        pipeline = build_intelligent_pipeline()
        pipeline.trace_store.record(_errored_trace())
        tool_runtime = build_tool_runtime()
        from core.platform_introspection import PlatformIntrospection

        qa = QAFramework(
            pipeline, tool_runtime,
            introspection=PlatformIntrospection(pipeline, tool_runtime),
        )
        report = await qa.run_full_qa()
        assert report["new_bug_count"] == 1
        assert report["validation"]["passed"] is True
        assert report["regressions"]["total"] == 1
        assert qa.get_reports()[0]["report_id"] == report["report_id"]

    async def test_validation_without_introspection_is_honest(self) -> None:
        qa = QAFramework(build_intelligent_pipeline())
        result = await qa.run_validation()
        assert result["available"] is False


class TestBugLifecycle:
    def test_close_and_filters(self) -> None:
        pipeline = build_intelligent_pipeline()
        pipeline.trace_store.record(_errored_trace())
        qa = QAFramework(pipeline)
        bug = qa.discover()[0]
        assert qa.list_bugs(status="open")[0].bug_id == bug.bug_id
        qa.close_bug(bug.bug_id)
        assert qa.list_bugs(status="open") == []
        assert qa.list_bugs(status="closed")[0].bug_id == bug.bug_id
        assert qa.list_bugs(source="pipeline")[0].bug_id == bug.bug_id

    def test_close_unknown_raises(self) -> None:
        qa = QAFramework(build_intelligent_pipeline())
        with pytest.raises(KeyError):
            qa.close_bug("ghost")


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


def _force_tool_failure(client: TestClient) -> None:
    client.post("/api/v1/tools/fs_read/execute",
                json={"parameters": {"path": "no_such_file.xyz"}})


class TestQAAPI:
    def test_clean_boot_no_bugs(self, client: TestClient) -> None:
        assert client.post("/api/v1/qa/discover").json()["count"] == 0
        assert client.get("/api/v1/qa/bugs").json()["count"] == 0

    def test_real_failure_discovered_via_api(self, client: TestClient) -> None:
        _force_tool_failure(client)
        discovered = client.post("/api/v1/qa/discover").json()
        assert discovered["count"] >= 1
        bug = discovered["new_bugs"][0]
        assert bug["source"] == "tool"
        detail = client.get(f"/api/v1/qa/bugs/{bug['bug_id']}").json()
        assert detail["evidence"]["tool_name"] == "fs_read"

    def test_reproduce_endpoint(self, client: TestClient) -> None:
        _force_tool_failure(client)
        bug = client.post("/api/v1/qa/discover").json()["new_bugs"][0]
        resp = client.post(f"/api/v1/qa/bugs/{bug['bug_id']}/reproduce")
        assert resp.status_code == 200
        assert resp.json()["status"] in ("reproduced", "not_reproducible")

    def test_full_qa_run_endpoint(self, client: TestClient) -> None:
        report = client.post("/api/v1/qa/run").json()
        assert report["kind"] == "full_qa"
        assert report["validation"]["passed"] is True
        reports = client.get("/api/v1/qa/reports").json()
        assert reports["count"] >= 1

    def test_unknown_bug_404(self, client: TestClient) -> None:
        assert client.get("/api/v1/qa/bugs/ghost").status_code == 404
        assert client.post("/api/v1/qa/bugs/ghost/reproduce").status_code == 404
        assert client.post("/api/v1/qa/bugs/ghost/close").status_code == 404
