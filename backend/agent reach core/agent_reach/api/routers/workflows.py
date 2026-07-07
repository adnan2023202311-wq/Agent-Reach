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

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_workflow_registry, get_workflow_engine

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


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
