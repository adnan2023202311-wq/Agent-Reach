"""
API layer: /api/v1/workflows — workflow execution and history.

Layer: Interface/Presentation.

Provides endpoints for:
- listing registered workflows
- executing a workflow (sync or async)
- retrieving workflow run results
- workflow history

Reuses the M5 WorkflowEngine and WorkflowRegistry. The registry is
built in the composition root and stored on app.state.

Route order matters: /runs must be defined before /{name} so it
isn't captured by the {name} path parameter.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from api.dependencies import get_workflow_registry, get_workflow_engine

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


def _run_manager(request: Request):
    manager = getattr(request.app.state, "workflow_run_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Workflow run manager not available")
    return manager


def _require_run(manager, run_id: str):
    run = manager.get(run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Run '{run_id}' not found.", "code": "RUN_NOT_FOUND"},
        )
    return run


@router.get("")
async def list_workflows(
    registry=Depends(get_workflow_registry),
) -> list[dict[str, Any]]:
    """List all registered workflows (summary)."""
    return [
        {
            "workflow_id": wf.workflow_id,
            "name": wf.name,
            "description": wf.description,
            "version": wf.version,
            "step_count": len(wf.steps),
            "created_at": wf.created_at,
        }
        for wf in registry.list_workflows()
    ]


@router.get("/runs")
async def list_workflow_runs(
    engine=Depends(get_workflow_engine),
) -> list[dict[str, Any]]:
    """Return all stored workflow run results."""
    return [r.to_dict() for r in engine.list_results()]


@router.get("/managed-runs")
async def list_managed_runs(request: Request, state: Optional[str] = None) -> dict[str, Any]:
    """List managed runs, newest first (M9.10)."""
    manager = _run_manager(request)
    from workflows.run_manager import RunState

    run_state = None
    if state:
        try:
            run_state = RunState(state)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"Unknown state '{state}'. Valid: {[s.value for s in RunState]}",
                    "code": "INVALID_STATE",
                },
            ) from exc
    runs = manager.list_runs(state=run_state)
    return {"runs": [r.to_dict() for r in runs], "count": len(runs)}


@router.get("/managed-runs/metrics")
async def managed_run_metrics(request: Request) -> dict[str, Any]:
    """Aggregate run metrics (M9.10)."""
    return _run_manager(request).get_metrics()


@router.get("/managed-runs/{run_id}")
async def get_managed_run(run_id: str, request: Request) -> dict[str, Any]:
    """One managed run's full detail including logs (M9.10)."""
    return _require_run(_run_manager(request), run_id).to_dict()


@router.get("/managed-runs/{run_id}/timeline")
async def managed_run_timeline(run_id: str, request: Request) -> dict[str, Any]:
    """Time-ordered lifecycle + step timeline for a run (M9.10)."""
    run = _require_run(_run_manager(request), run_id)
    return {"run_id": run_id, "timeline": run.timeline()}


@router.post("/managed-runs/{run_id}/pause")
async def pause_managed_run(run_id: str, request: Request) -> dict[str, Any]:
    """Pause a running workflow at the next step boundary (M9.10)."""
    manager = _run_manager(request)
    _require_run(manager, run_id)
    from workflows.run_manager import InvalidRunTransition

    try:
        return manager.pause(run_id).to_dict()
    except InvalidRunTransition as exc:
        raise HTTPException(
            status_code=409, detail={"message": str(exc), "code": "INVALID_TRANSITION"}
        ) from exc


@router.post("/managed-runs/{run_id}/resume")
async def resume_managed_run(run_id: str, request: Request) -> dict[str, Any]:
    """Resume a paused workflow (M9.10)."""
    manager = _run_manager(request)
    _require_run(manager, run_id)
    from workflows.run_manager import InvalidRunTransition

    try:
        return manager.resume(run_id).to_dict()
    except InvalidRunTransition as exc:
        raise HTTPException(
            status_code=409, detail={"message": str(exc), "code": "INVALID_TRANSITION"}
        ) from exc


@router.post("/managed-runs/{run_id}/cancel")
async def cancel_managed_run(run_id: str, request: Request) -> dict[str, Any]:
    """Cancel a running/paused workflow at the next step boundary (M9.10)."""
    manager = _run_manager(request)
    _require_run(manager, run_id)
    from workflows.run_manager import InvalidRunTransition

    try:
        return manager.cancel(run_id).to_dict()
    except InvalidRunTransition as exc:
        raise HTTPException(
            status_code=409, detail={"message": str(exc), "code": "INVALID_TRANSITION"}
        ) from exc


@router.post("/managed-runs/{run_id}/retry")
async def retry_managed_run(
    run_id: str,
    request: Request,
    registry=Depends(get_workflow_registry),
) -> dict[str, Any]:
    """Start a fresh run of a finished run's workflow (M9.10)."""
    manager = _run_manager(request)
    source = _require_run(manager, run_id)
    workflow = registry.get(source.workflow_name)
    if workflow is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"Workflow '{source.workflow_name}' is no longer registered.",
                "code": "WORKFLOW_NOT_FOUND",
            },
        )
    from workflows.run_manager import InvalidRunTransition

    try:
        run = await manager.retry(run_id, workflow)
    except InvalidRunTransition as exc:
        raise HTTPException(
            status_code=409, detail={"message": str(exc), "code": "INVALID_TRANSITION"}
        ) from exc
    return run.to_dict()


@router.post("/{name}/start")
async def start_workflow_managed(
    name: str,
    request: Request,
    variables: Optional[dict[str, Any]] = None,
    registry=Depends(get_workflow_registry),
) -> dict[str, Any]:
    """Start a workflow as a managed background run (M9.10).

    Unlike POST /{name}/run (which awaits completion), this returns
    immediately with a run_id that supports pause/resume/cancel/retry
    and exposes timeline, logs, and metrics.
    """
    wf = registry.get(name)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")
    manager = _run_manager(request)
    run = await manager.start(wf, variables)
    return {"run_id": run.run_id, "state": run.state.value, "workflow_id": run.workflow_id}


@router.post("/{name}/run")
async def run_workflow(
    name: str,
    variables: Optional[dict[str, Any]] = None,
    engine=Depends(get_workflow_engine),
    registry=Depends(get_workflow_registry),
) -> dict[str, Any]:
    """Execute a workflow and return the result."""
    wf = registry.get(name)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")

    try:
        result = await engine.run(wf, variables)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return result.to_dict()


@router.get("/{name}")
async def get_workflow(
    name: str,
    registry=Depends(get_workflow_registry),
) -> dict[str, Any]:
    """Return the full definition of a workflow by name."""
    wf = registry.get(name)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")
    return wf.to_dict()


@router.get("/runs/{workflow_id}")
async def get_workflow_result(
    workflow_id: str,
    engine=Depends(get_workflow_engine),
) -> dict[str, Any]:
    """Return the result of a workflow run by workflow_id."""
    result = engine.get_result(workflow_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No result found for workflow_id '{workflow_id}'",
        )
    return result.to_dict()
