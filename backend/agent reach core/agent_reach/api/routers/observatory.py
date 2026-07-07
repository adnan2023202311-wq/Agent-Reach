"""
API layer: /api/v1/observatory — Live Execution Observatory (M8.6)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from api.dependencies import get_pipeline, get_controller

router = APIRouter(prefix="/api/v1/observatory", tags=["observatory"])


@router.get("/live")
async def live_execution(pipeline=Depends(get_pipeline), controller=Depends(get_controller)) -> dict[str, Any]:
    """Real-time execution dashboard data."""
    # pipeline stats
    pipe_stats = {}
    trace_last = {}
    if pipeline:
        try:
            pipe_stats = pipeline.get_stats()
            # verify_integration gives subsystem health
            integration = pipeline.verify_integration()
        except Exception:
            integration = {"subsystems": {}, "active_count": 0}
    else:
        integration = {"subsystems": {}, "active_count": 0}

    # controller / dispatcher metrics
    agent_types = []
    try:
        agent_types = [t.value for t in controller.registered_agent_types()]
    except Exception:
        pass

    return {
        "timestamp": __import__("time").time(),
        "pipeline": pipe_stats,
        "integration": integration,
        "agents": agent_types,
        "router": integration.get("subsystems", {}).get("router", {}),
        "memory": integration.get("subsystems", {}).get("memory", {}),
        "context": integration.get("subsystems", {}).get("context", {}),
        "moa": integration.get("subsystems", {}).get("moa", {}),
        "reflection": integration.get("subsystems", {}).get("reflection", {}),
        "knowledge_graph": integration.get("subsystems", {}).get("knowledge_graph", {}),
        "learning": integration.get("subsystems", {}).get("learning", {}),
        "tutti": integration.get("subsystems", {}).get("tutti", {}),
        "status": "live",
    }


@router.get("/trace/{request_id}")
async def get_trace(request_id: str) -> dict[str, Any]:
    """Fetch a specific execution trace – stub for now (stateless)."""
    return {
        "request_id": request_id,
        "found": False,
        "message": "Trace persistence is a future Milestone 8.5 enhancement – currently traces are in-memory per request.",
    }


@router.get("/metrics")
async def observatory_metrics(pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    if not pipeline:
        return {"error": "pipeline unavailable"}
    try:
        s = pipeline.get_stats()
        integration = pipeline.verify_integration()
        return {
            "total_requests": s.get("total_requests", 0),
            "avg_latency_ms": s.get("avg_latency_ms", 0),
            "active_subsystems": integration.get("active_count", 0),
            "subsystems": integration.get("subsystems", {}),
        }
    except Exception as exc:
        return {"error": str(exc)}
