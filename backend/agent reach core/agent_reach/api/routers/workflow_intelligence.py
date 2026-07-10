"""
API layer: /api/v1/workflows/intelligence — Workflow Intelligence (M10.38).

Auto-optimization and predictions for workflows. Analyzes execution
patterns, predicts outcomes, and suggests optimizations.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/workflows/intelligence", tags=["workflow-intelligence"])


class WorkflowExecution(BaseModel):
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    duration_ms: float = 0.0
    success: bool = True
    node_count: int = 0
    error_count: int = 0
    timestamp: float = Field(default_factory=time.time)


class OptimizationSuggestion(BaseModel):
    suggestion_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    suggestion_type: str  # merge_nodes | parallelize | remove_redundant | cache_step
    description: str = ""
    estimated_improvement: str = ""  # e.g. "30% faster", "50% less API calls"
    confidence: float = 0.5
    created_at: float = Field(default_factory=time.time)


class WorkflowPrediction(BaseModel):
    prediction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    predicted_duration_ms: float = 0.0
    predicted_success: bool = True
    confidence: float = 0.5
    factors: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


_executions: list[WorkflowExecution] = []
_suggestions: dict[str, OptimizationSuggestion] = {}
_predictions: dict[str, WorkflowPrediction] = {}


class RecordExecutionRequest(BaseModel):
    workflow_id: str
    duration_ms: float = 0.0
    success: bool = True
    node_count: int = 0
    error_count: int = 0


@router.post("/executions")
async def record_execution(request: RecordExecutionRequest) -> dict[str, Any]:
    """Record a workflow execution for analysis."""
    execution = WorkflowExecution(
        workflow_id=request.workflow_id, duration_ms=request.duration_ms,
        success=request.success, node_count=request.node_count, error_count=request.error_count,
    )
    _executions.append(execution)
    if len(_executions) > 1000:
        _executions[:] = _executions[-500:]
    return {"execution_id": execution.execution_id, "status": "recorded"}


@router.get("/executions")
async def list_executions(workflow_id: Optional[str] = None, limit: int = 20) -> dict[str, Any]:
    execs = list(_executions)
    if workflow_id:
        execs = [e for e in execs if e.workflow_id == workflow_id]
    return {"executions": [e.model_dump() for e in execs[-limit:]], "count": len(execs)}


@router.get("/optimize/{workflow_id}")
async def suggest_optimizations(workflow_id: str) -> dict[str, Any]:
    """Suggest optimizations for a workflow based on execution history."""
    wf_execs = [e for e in _executions if e.workflow_id == workflow_id]
    suggestions: list[OptimizationSuggestion] = []

    if not wf_execs:
        return {"workflow_id": workflow_id, "suggestions": [], "status": "no_data"}

    # Analyze success rate
    success_rate = sum(1 for e in wf_execs if e.success) / len(wf_execs)
    if success_rate < 0.8:
        suggestions.append(OptimizationSuggestion(
            workflow_id=workflow_id, suggestion_type="add_error_handling",
            description=f"Success rate is {success_rate:.0%}. Add error handling nodes to improve reliability.",
            estimated_improvement=f"+{(1 - success_rate) * 100:.0f}% success rate",
            confidence=0.8,
        ))

    # Analyze duration
    avg_duration = sum(e.duration_ms for e in wf_execs) / len(wf_execs)
    if avg_duration > 5000:
        suggestions.append(OptimizationSuggestion(
            workflow_id=workflow_id, suggestion_type="parallelize",
            description=f"Average duration is {avg_duration:.0f}ms. Consider parallelizing independent nodes.",
            estimated_improvement="30-50% faster",
            confidence=0.7,
        ))

    # Analyze node count
    avg_nodes = sum(e.node_count for e in wf_execs) / len(wf_execs)
    if avg_nodes > 10:
        suggestions.append(OptimizationSuggestion(
            workflow_id=workflow_id, suggestion_type="merge_nodes",
            description=f"Workflow has {avg_nodes:.0f} nodes on average. Consider merging related nodes.",
            estimated_improvement="Simpler workflow",
            confidence=0.6,
        ))

    # Cache suggestion
    if len(wf_execs) > 5:
        suggestions.append(OptimizationSuggestion(
            workflow_id=workflow_id, suggestion_type="cache_step",
            description="This workflow runs frequently. Consider caching intermediate results.",
            estimated_improvement="50% less API calls on repeated runs",
            confidence=0.5,
        ))

    for s in suggestions:
        _suggestions[s.suggestion_id] = s

    return {
        "workflow_id": workflow_id,
        "suggestions": [s.model_dump() for s in suggestions],
        "count": len(suggestions),
        "based_on": f"{len(wf_execs)} executions",
    }


@router.post("/predict/{workflow_id}")
async def predict_outcome(workflow_id: str) -> dict[str, Any]:
    """Predict the outcome of a workflow execution."""
    wf_execs = [e for e in _executions if e.workflow_id == workflow_id]
    if not wf_execs:
        prediction = WorkflowPrediction(
            workflow_id=workflow_id, confidence=0.0,
            factors={"reason": "no_historical_data"},
        )
    else:
        avg_duration = sum(e.duration_ms for e in wf_execs) / len(wf_execs)
        success_rate = sum(1 for e in wf_execs if e.success) / len(wf_execs)
        prediction = WorkflowPrediction(
            workflow_id=workflow_id,
            predicted_duration_ms=round(avg_duration, 2),
            predicted_success=success_rate > 0.5,
            confidence=round(min(1.0, len(wf_execs) / 20.0), 2),
            factors={
                "historical_executions": len(wf_execs),
                "success_rate": round(success_rate, 4),
                "avg_duration_ms": round(avg_duration, 2),
            },
        )
    _predictions[prediction.prediction_id] = prediction
    return prediction.model_dump()


@router.get("/stats")
async def workflow_intelligence_stats() -> dict[str, Any]:
    total_execs = len(_executions)
    successful = sum(1 for e in _executions if e.success)
    avg_duration = sum(e.duration_ms for e in _executions) / max(1, total_execs)
    return {
        "total_executions": total_execs,
        "success_rate": round(successful / max(1, total_execs), 4),
        "avg_duration_ms": round(avg_duration, 2),
        "suggestions_generated": len(_suggestions),
        "predictions_made": len(_predictions),
    }
