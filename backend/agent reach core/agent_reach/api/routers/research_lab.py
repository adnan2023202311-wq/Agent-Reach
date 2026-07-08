"""
API layer: /api/v1/research-lab — AI Research Laboratory (M9.28).

Layer: Interface/Presentation.

Exposes the ResearchLab: controlled experiment definition (pipeline
configs, prompts, memory policies), execution with real measurements
per variant, and metric-declared winner selection.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/research-lab", tags=["research-lab"])


class ExperimentCreate(BaseModel):
    kind: str = Field(min_length=1)
    name: str = Field(min_length=1)
    tasks: list[str] = Field(min_length=1)
    variants: dict[str, dict[str, Any]] = Field(min_length=2)
    metric: str = ""


def _lab(request: Request):
    lab = getattr(request.app.state, "research_lab", None)
    if lab is None:
        raise HTTPException(status_code=503, detail="Research lab not available")
    return lab


@router.post("/experiments")
async def define_experiment(body: ExperimentCreate, request: Request) -> dict[str, Any]:
    try:
        return _lab(request).define(
            body.kind, body.name, body.tasks, body.variants, metric=body.metric
        ).to_dict()
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "code": "INVALID_EXPERIMENT"},
        ) from exc


@router.post("/experiments/{experiment_id}/run")
async def run_experiment(experiment_id: str, request: Request) -> dict[str, Any]:
    try:
        return (await _lab(request).run(experiment_id)).to_dict()
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"message": str(exc.args[0]), "code": "EXPERIMENT_NOT_FOUND"},
        ) from exc


@router.get("/experiments")
async def list_experiments(request: Request, limit: int = 20) -> dict[str, Any]:
    experiments = _lab(request).list_experiments(limit=limit)
    return {"experiments": [e.to_dict() for e in experiments], "count": len(experiments)}


@router.get("/experiments/{experiment_id}")
async def get_experiment(experiment_id: str, request: Request) -> dict[str, Any]:
    experiment = _lab(request).get(experiment_id)
    if experiment is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Experiment '{experiment_id}' not found.", "code": "EXPERIMENT_NOT_FOUND"},
        )
    return experiment.to_dict()
