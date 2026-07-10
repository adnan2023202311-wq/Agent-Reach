"""
API layer: /api/v1/monitoring — Production Monitoring Center (M10.13).

Centralized monitoring of running agents, active workflows, costs,
latency, provider health, errors, and events. Aggregates data from
the existing M9.3 trace store, M9.24 event hub, and the M10.1 node
registry.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request

from api.dependencies import get_pipeline

router = APIRouter(prefix="/api/v1/monitoring", tags=["production-monitoring"])


@router.get("/dashboard")
async def monitoring_dashboard(
    request: Request,
    pipeline: Any = Depends(get_pipeline),
) -> dict[str, Any]:
    """Centralized monitoring dashboard — all systems at a glance."""
    # Gather from existing subsystems
    trace_store = getattr(pipeline, "_trace_store", None)
    traces = trace_store.list_traces(limit=100) if trace_store else []

    total_requests = len(traces)
    successful = sum(1 for t in traces if not t.errors)
    failed = total_requests - successful
    avg_latency = sum(t.total_latency_ms for t in traces) / max(1, total_requests)

    # Provider usage from traces
    provider_usage: dict[str, int] = {}
    for t in traces:
        if t.router_provider:
            provider_usage[t.router_provider] = provider_usage.get(t.router_provider, 0) + 1

    # Node registry stats (M10.1)
    node_stats: dict[str, Any] = {}
    try:
        from distributed import get_node_registry
        node_stats = get_node_registry().cluster_stats()
    except Exception:
        pass

    # Pipeline stats
    pipeline_stats = pipeline.get_stats() if hasattr(pipeline, "get_stats") else {}

    # Active sessions
    session_manager = getattr(request.app.state, "session_manager", None)
    active_sessions = len(session_manager._sessions) if session_manager and hasattr(session_manager, "_sessions") else 0

    return {
        "timestamp": time.time(),
        "requests": {
            "total": total_requests,
            "successful": successful,
            "failed": failed,
            "success_rate": round(successful / max(1, total_requests), 4),
            "avg_latency_ms": round(avg_latency, 2),
        },
        "providers": {
            "usage": provider_usage,
            "active": list(provider_usage.keys()),
        },
        "cluster": node_stats,
        "pipeline": pipeline_stats,
        "sessions": {"active": active_sessions},
        "subsystems": pipeline.get_live_status() if hasattr(pipeline, "get_live_status") else {},
    }


@router.get("/traces")
async def recent_traces(
    pipeline: Any = Depends(get_pipeline),
    limit: int = 20,
) -> dict[str, Any]:
    """Recent execution traces for debugging."""
    trace_store = getattr(pipeline, "_trace_store", None)
    if trace_store is None:
        return {"traces": [], "count": 0}
    traces = trace_store.list_traces(limit=limit)
    return {
        "traces": [t.to_dict() for t in traces],
        "count": len(traces),
    }


@router.get("/errors")
async def error_summary(
    pipeline: Any = Depends(get_pipeline),
    limit: int = 50,
) -> dict[str, Any]:
    """Recent errors across all executions."""
    trace_store = getattr(pipeline, "_trace_store", None)
    if trace_store is None:
        return {"errors": [], "count": 0}
    traces = trace_store.list_traces(limit=limit)
    errors = []
    for t in traces:
        for err in t.errors:
            errors.append({
                "request_id": t.request_id,
                "timestamp": t.timestamp,
                "provider": t.router_provider,
                "error": err,
            })
    return {"errors": errors, "count": len(errors)}


@router.get("/costs")
async def cost_summary(
    pipeline: Any = Depends(get_pipeline),
) -> dict[str, Any]:
    """Estimated cost breakdown by provider."""
    trace_store = getattr(pipeline, "_trace_store", None)
    if trace_store is None:
        return {"costs": {}, "total": 0.0}
    traces = trace_store.list_traces(limit=500)
    costs: dict[str, float] = {}
    for t in traces:
        if t.router_provider:
            costs[t.router_provider] = costs.get(t.router_provider, 0.0) + (t.total_latency_ms / 1000.0) * 0.001
    return {
        "costs": {k: round(v, 4) for k, v in costs.items()},
        "total": round(sum(costs.values()), 4),
        "currency": "USD (estimated)",
        "note": "Costs are estimated from latency × a rough per-second rate. Real billing requires provider integration.",
    }


@router.get("/health")
async def health_check(request: Request) -> dict[str, Any]:
    """Comprehensive health check of all subsystems."""
    checks: dict[str, dict[str, Any]] = {}
    # Pipeline
    pipeline = getattr(request.app.state, "pipeline", None)
    checks["pipeline"] = {"status": "healthy" if pipeline else "down", "latency_ms": 0}
    # Controller
    controller = getattr(request.app.state, "controller", None)
    checks["controller"] = {"status": "healthy" if controller else "down"}
    # Conversation engine
    conv_engine = getattr(request.app.state, "conversation_engine", None)
    checks["conversation_engine"] = {"status": "healthy" if conv_engine else "down"}
    # Tool runtime
    tool_runtime = getattr(request.app.state, "tool_runtime", None)
    checks["tool_runtime"] = {"status": "healthy" if tool_runtime else "down"}
    # Event hub
    event_hub = getattr(request.app.state, "event_hub", None)
    checks["event_hub"] = {"status": "healthy" if event_hub else "down"}
    # Node registry
    try:
        from distributed import get_node_registry
        node_stats = get_node_registry().cluster_stats()
        checks["node_registry"] = {"status": "healthy", "nodes": node_stats["total_nodes"]}
    except Exception:
        checks["node_registry"] = {"status": "down"}

    all_healthy = all(c["status"] == "healthy" for c in checks.values())
    return {
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks,
        "timestamp": time.time(),
    }
