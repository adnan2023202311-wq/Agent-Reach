"""
API layer: /api/v1/benchmark-lab — Autonomous Benchmark Laboratory (M9.19).

Layer: Interface/Presentation.

Exposes the ProviderBenchmarkLab: verifiable task suites, real
provider runs, and the routing updates each run applied to the SHARED
router (the pipeline's instance — scoring immediately reflects lab
results).
"""

from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/benchmark-lab", tags=["benchmark-lab"])


class LabRunRequest(BaseModel):
    providers: List[str] = Field(min_length=1)


def _lab(request: Request):
    lab = getattr(request.app.state, "benchmark_lab", None)
    if lab is None:
        raise HTTPException(status_code=503, detail="Benchmark lab not available")
    return lab


@router.get("/tasks")
async def list_tasks(request: Request) -> dict[str, Any]:
    """The verifiable task suite (id, category, description)."""
    tasks = _lab(request).tasks
    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "category": t.category,
                "description": t.description,
            }
            for t in tasks
        ],
        "count": len(tasks),
    }


@router.post("/run")
async def run_lab(body: LabRunRequest, request: Request) -> dict[str, Any]:
    """Benchmark providers on the verifiable suite; update routing."""
    lab = _lab(request)
    try:
        run = await lab.run(body.providers)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "code": "INVALID_LAB_REQUEST"},
        ) from exc
    return run.to_dict()


@router.get("/runs")
async def list_runs(request: Request, limit: int = 20) -> dict[str, Any]:
    """Past lab runs, newest first."""
    runs = _lab(request).get_runs(limit=limit)
    return {"runs": [r.to_dict() for r in runs], "count": len(runs)}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> dict[str, Any]:
    run = _lab(request).get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Lab run '{run_id}' not found.", "code": "RUN_NOT_FOUND"},
        )
    return run.to_dict()
