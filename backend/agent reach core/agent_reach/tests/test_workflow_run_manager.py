"""Tests for M9.10 — Runtime Workflow Engine (WorkflowRunManager).

Covers: managed start/wait, pause at step boundaries, resume, cancel
(engine records CANCELLED), retry with lineage, timeline/logs/metrics,
invalid transitions, and the /api/v1/workflows managed-run endpoints.

Workflows here use TOOL steps against a locally registered tool so
runs are deterministic and need no model provider.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from config.settings import get_settings
from core.tool_executor import ToolExecutor
from infrastructure.tool_manager import ToolManager
from workflows.engine import WorkflowEngine
from workflows.models import StepType, Workflow, WorkflowStep, WorkflowState
from workflows.orchestration import ToolOrchestrator
from workflows.run_manager import (
    InvalidRunTransition,
    RunState,
    WorkflowRunManager,
)


# ===========================================================================
# Helpers
# ===========================================================================


class _StepProbe:
    """Deterministic tool: counts calls and can block on an event.

    ``entered`` is set as soon as any call begins, letting tests wait
    until a step is genuinely executing before pausing/cancelling.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.release = asyncio.Event()
        self.release.set()
        self.entered = asyncio.Event()

    async def __call__(self, tag: str = "") -> str:
        self.entered.set()
        await self.release.wait()
        self.calls.append(tag)
        return f"done:{tag}"


def _build_manager(probe: _StepProbe) -> WorkflowRunManager:
    manager = ToolManager()
    manager.register("probe", probe)
    engine = WorkflowEngine(
        tool_orchestrator=ToolOrchestrator(executor=ToolExecutor(manager))
    )
    return WorkflowRunManager(engine)


def _three_step_workflow(name: str = "wf-three") -> Workflow:
    return Workflow(
        name=name,
        steps=[
            WorkflowStep(step_id=f"s{i}", type=StepType.TOOL, target="probe",
                         inputs={"tag": f"s{i}"}, output_keys=[])
            for i in (1, 2, 3)
        ],
    )


# ===========================================================================
# Lifecycle
# ===========================================================================


@pytest.mark.asyncio
class TestRunLifecycle:
    async def test_start_and_complete(self) -> None:
        probe = _StepProbe()
        manager = _build_manager(probe)
        run = await manager.start(_three_step_workflow())
        run = await manager.wait(run.run_id, timeout=5)
        assert run.state == RunState.COMPLETED
        assert probe.calls == ["s1", "s2", "s3"]
        assert run.result is not None
        assert run.result.state == WorkflowState.COMPLETED
        assert run.finished_at is not None

    async def test_result_lands_in_shared_engine(self) -> None:
        probe = _StepProbe()
        manager = _build_manager(probe)
        wf = _three_step_workflow()
        run = await manager.start(wf)
        await manager.wait(run.run_id, timeout=5)
        # The SAME engine instance holds the result (no parallel store).
        assert manager.engine.get_result(wf.workflow_id) is not None

    async def test_pause_blocks_next_step_then_resume(self) -> None:
        probe = _StepProbe()
        probe.release.clear()  # block step 1 mid-flight
        manager = _build_manager(probe)
        run = await manager.start(_three_step_workflow())

        # Wait until step 1 is genuinely executing, THEN pause — so the
        # pause lands at the s1→s2 boundary, not before s1's gate.
        await asyncio.wait_for(probe.entered.wait(), timeout=5)
        manager.pause(run.run_id)
        assert manager.get(run.run_id).state == RunState.PAUSED

        probe.release.set()  # finish step 1; gate must hold step 2
        await asyncio.sleep(0.1)
        assert probe.calls == ["s1"]  # paused before s2

        manager.resume(run.run_id)
        run = await manager.wait(run.run_id, timeout=5)
        assert run.state == RunState.COMPLETED
        assert probe.calls == ["s1", "s2", "s3"]

    async def test_cancel_stops_at_step_boundary(self) -> None:
        probe = _StepProbe()
        probe.release.clear()
        manager = _build_manager(probe)
        wf = _three_step_workflow()
        run = await manager.start(wf)

        manager.cancel(run.run_id)
        probe.release.set()
        run = await manager.wait(run.run_id, timeout=5)
        assert run.state == RunState.CANCELLED
        # Engine recorded the partial run as CANCELLED too.
        engine_result = manager.engine.get_result(wf.workflow_id)
        assert engine_result is not None
        assert engine_result.state == WorkflowState.CANCELLED
        assert len(probe.calls) < 3

    async def test_cancel_while_paused(self) -> None:
        probe = _StepProbe()
        probe.release.clear()
        manager = _build_manager(probe)
        run = await manager.start(_three_step_workflow())
        manager.pause(run.run_id)
        probe.release.set()
        await asyncio.sleep(0.1)
        manager.cancel(run.run_id)
        run = await manager.wait(run.run_id, timeout=5)
        assert run.state == RunState.CANCELLED

    async def test_retry_links_lineage_and_reruns(self) -> None:
        probe = _StepProbe()
        manager = _build_manager(probe)
        wf = _three_step_workflow()
        first = await manager.start(wf, variables={"k": "v"})
        await manager.wait(first.run_id, timeout=5)

        second = await manager.retry(first.run_id, wf)
        second = await manager.wait(second.run_id, timeout=5)
        assert second.state == RunState.COMPLETED
        assert second.retry_of == first.run_id
        assert second.variables == {"k": "v"}
        assert probe.calls == ["s1", "s2", "s3"] * 2

    async def test_failed_workflow_marks_run_failed(self) -> None:
        manager = ToolManager()  # 'probe' NOT registered → step fails

        engine = WorkflowEngine(
            tool_orchestrator=ToolOrchestrator(executor=ToolExecutor(manager))
        )
        run_manager = WorkflowRunManager(engine)
        run = await run_manager.start(_three_step_workflow())
        run = await run_manager.wait(run.run_id, timeout=5)
        assert run.state == RunState.FAILED


# ===========================================================================
# Transitions & introspection
# ===========================================================================


@pytest.mark.asyncio
class TestTransitionsAndIntrospection:
    async def test_invalid_transitions_raise(self) -> None:
        probe = _StepProbe()
        manager = _build_manager(probe)
        run = await manager.start(_three_step_workflow())
        await manager.wait(run.run_id, timeout=5)

        with pytest.raises(InvalidRunTransition):
            manager.pause(run.run_id)  # already completed
        with pytest.raises(InvalidRunTransition):
            manager.resume(run.run_id)  # not paused
        with pytest.raises(InvalidRunTransition):
            manager.cancel(run.run_id)  # already completed

    async def test_retry_in_progress_rejected(self) -> None:
        probe = _StepProbe()
        probe.release.clear()
        manager = _build_manager(probe)
        wf = _three_step_workflow()
        run = await manager.start(wf)
        with pytest.raises(InvalidRunTransition):
            await manager.retry(run.run_id, wf)
        manager.cancel(run.run_id)
        probe.release.set()
        await manager.wait(run.run_id, timeout=5)

    async def test_unknown_run_raises_keyerror(self) -> None:
        probe = _StepProbe()
        manager = _build_manager(probe)
        with pytest.raises(KeyError):
            manager.pause("ghost")

    async def test_timeline_merges_lifecycle_and_steps(self) -> None:
        probe = _StepProbe()
        manager = _build_manager(probe)
        run = await manager.start(_three_step_workflow())
        run = await manager.wait(run.run_id, timeout=5)
        timeline = run.timeline()
        kinds = {e["kind"] for e in timeline}
        assert kinds == {"lifecycle", "step"}
        timestamps = [e["timestamp"] for e in timeline]
        assert timestamps == sorted(timestamps)
        step_events = [e for e in timeline if e["kind"] == "step"]
        assert len(step_events) == 3
        assert all(e["detail"] == "succeeded" for e in step_events)

    async def test_metrics_aggregate(self) -> None:
        probe = _StepProbe()
        manager = _build_manager(probe)
        wf = _three_step_workflow()
        r1 = await manager.start(wf)
        await manager.wait(r1.run_id, timeout=5)
        r2 = await manager.retry(r1.run_id, wf)
        await manager.wait(r2.run_id, timeout=5)
        metrics = manager.get_metrics()
        assert metrics["total_runs"] == 2
        assert metrics["completed"] == 2
        assert metrics["retries"] == 1
        assert metrics["avg_duration_ms"] > 0

    async def test_list_runs_newest_first_with_filter(self) -> None:
        probe = _StepProbe()
        manager = _build_manager(probe)
        wf = _three_step_workflow()
        r1 = await manager.start(wf)
        await manager.wait(r1.run_id, timeout=5)
        r2 = await manager.start(wf)
        await manager.wait(r2.run_id, timeout=5)
        runs = manager.list_runs()
        assert [r.run_id for r in runs] == [r2.run_id, r1.run_id]
        assert len(manager.list_runs(state=RunState.COMPLETED)) == 2
        assert manager.list_runs(state=RunState.FAILED) == []


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


def _register_tool_workflow(client: TestClient) -> str:
    """Register a workflow whose TOOL step uses a locally registered tool."""

    async def echo(**kwargs: Any) -> str:
        return "echoed"

    engine = client.app.state.workflow_engine
    engine.tool_orchestrator.executor.register_tool("echo", echo)
    wf = Workflow(
        name="api-managed-wf",
        steps=[
            WorkflowStep(step_id="s1", type=StepType.TOOL, target="echo",
                         inputs={}, output_keys=[]),
        ],
    )
    client.app.state.workflow_registry.register(wf)
    return wf.name


class TestManagedRunAPI:
    def test_start_returns_run_id(self, client: TestClient) -> None:
        name = _register_tool_workflow(client)
        resp = client.post(f"/api/v1/workflows/{name}/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"]
        assert data["state"] in ("running", "completed")

    def test_start_unknown_workflow_404(self, client: TestClient) -> None:
        assert client.post("/api/v1/workflows/ghost/start").status_code == 404

    def test_run_detail_and_listing(self, client: TestClient) -> None:
        name = _register_tool_workflow(client)
        run_id = client.post(f"/api/v1/workflows/{name}/start").json()["run_id"]
        detail = client.get(f"/api/v1/workflows/managed-runs/{run_id}")
        assert detail.status_code == 200
        assert detail.json()["run_id"] == run_id
        listing = client.get("/api/v1/workflows/managed-runs").json()
        assert any(r["run_id"] == run_id for r in listing["runs"])

    def test_timeline_endpoint(self, client: TestClient) -> None:
        name = _register_tool_workflow(client)
        run_id = client.post(f"/api/v1/workflows/{name}/start").json()["run_id"]
        # Poll until the background task completes.
        for _ in range(50):
            if client.get(
                f"/api/v1/workflows/managed-runs/{run_id}"
            ).json()["state"] != "running":
                break
        resp = client.get(f"/api/v1/workflows/managed-runs/{run_id}/timeline")
        assert resp.status_code == 200
        assert len(resp.json()["timeline"]) >= 1

    def test_metrics_endpoint(self, client: TestClient) -> None:
        name = _register_tool_workflow(client)
        client.post(f"/api/v1/workflows/{name}/start")
        resp = client.get("/api/v1/workflows/managed-runs/metrics")
        assert resp.status_code == 200
        assert resp.json()["total_runs"] >= 1

    def test_unknown_run_404(self, client: TestClient) -> None:
        assert client.get("/api/v1/workflows/managed-runs/ghost").status_code == 404
        assert client.post("/api/v1/workflows/managed-runs/ghost/pause").status_code == 404

    def test_invalid_state_filter_422(self, client: TestClient) -> None:
        resp = client.get("/api/v1/workflows/managed-runs?state=warp")
        assert resp.status_code == 422

    def test_invalid_transition_409(self, client: TestClient) -> None:
        name = _register_tool_workflow(client)
        run_id = client.post(f"/api/v1/workflows/{name}/start").json()["run_id"]
        for _ in range(50):
            if client.get(
                f"/api/v1/workflows/managed-runs/{run_id}"
            ).json()["state"] != "running":
                break
        resp = client.post(f"/api/v1/workflows/managed-runs/{run_id}/resume")
        assert resp.status_code == 409

    def test_retry_endpoint(self, client: TestClient) -> None:
        name = _register_tool_workflow(client)
        run_id = client.post(f"/api/v1/workflows/{name}/start").json()["run_id"]
        for _ in range(50):
            if client.get(
                f"/api/v1/workflows/managed-runs/{run_id}"
            ).json()["state"] != "running":
                break
        resp = client.post(f"/api/v1/workflows/managed-runs/{run_id}/retry")
        assert resp.status_code == 200
        assert resp.json()["retry_of"] == run_id

    def test_legacy_run_endpoint_still_works(self, client: TestClient) -> None:
        """Backward compatibility: POST /{name}/run awaits completion."""
        name = _register_tool_workflow(client)
        resp = client.post(f"/api/v1/workflows/{name}/run")
        assert resp.status_code == 200
        assert resp.json()["state"] == "completed"
