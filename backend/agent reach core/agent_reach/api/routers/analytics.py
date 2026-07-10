"""
API layer: /api/v1/analytics — Advanced Analytics (M10.36).

Cross-subsystem metrics, insights, and trends. Aggregates data from
all M10 subsystems to provide platform-wide intelligence.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request

from api.dependencies import get_pipeline

router = APIRouter(prefix="/api/v1/analytics", tags=["advanced-analytics"])


@router.get("/overview")
async def analytics_overview(
    request: Request,
    pipeline: Any = Depends(get_pipeline),
) -> dict[str, Any]:
    """Platform-wide analytics overview."""
    # Gather from all subsystems
    trace_store = getattr(pipeline, "_trace_store", None)
    traces = trace_store.list_traces(limit=500) if trace_store else []

    # Execution metrics
    total_executions = len(traces)
    successful = sum(1 for t in traces if not t.errors)
    failed = total_executions - successful

    # Provider distribution
    provider_dist: dict[str, int] = {}
    for t in traces:
        if t.router_provider:
            provider_dist[t.router_provider] = provider_dist.get(t.router_provider, 0) + 1

    # Latency trend
    latency_trend = [round(t.total_latency_ms, 2) for t in traces[-20:]] if traces else []

    # Node cluster
    try:
        from distributed import get_node_registry
        cluster = get_node_registry().cluster_stats()
    except Exception:
        cluster = {}

    # Pipeline stats
    pipeline_stats = pipeline.get_stats() if hasattr(pipeline, "get_stats") else {}

    # Subsystem live status
    live_status = pipeline.get_live_status() if hasattr(pipeline, "get_live_status") else {}

    return {
        "timestamp": time.time(),
        "execution": {
            "total": total_executions,
            "successful": successful,
            "failed": failed,
            "success_rate": round(successful / max(1, total_executions), 4),
        },
        "providers": {
            "distribution": provider_dist,
            "active_count": len(provider_dist),
        },
        "performance": {
            "avg_latency_ms": round(sum(t.total_latency_ms for t in traces) / max(1, total_executions), 2),
            "latency_trend": latency_trend,
            "p95_latency_ms": round(sorted([t.total_latency_ms for t in traces])[int(len(traces) * 0.95)] if traces else 0, 2),
        },
        "cluster": cluster,
        "pipeline": pipeline_stats,
        "subsystems": live_status,
    }


@router.get("/trends")
async def analytics_trends(
    pipeline: Any = Depends(get_pipeline),
    window: int = 100,
) -> dict[str, Any]:
    """Trend analysis over recent executions."""
    trace_store = getattr(pipeline, "_trace_store", None)
    if trace_store is None:
        return {"trends": {}, "status": "no_data"}
    traces = trace_store.list_traces(limit=window)
    if not traces:
        return {"trends": {}, "status": "no_data"}

    # Latency trend
    latencies = [t.total_latency_ms for t in traces]
    avg_latency = sum(latencies) / len(latencies)
    recent_avg = sum(latencies[-10:]) / max(1, len(latencies[-10:]))
    latency_direction = "improving" if recent_avg < avg_latency else "degrading"

    # Error trend
    errors = [len(t.errors) for t in traces]
    error_rate = sum(1 for e in errors if e > 0) / len(errors)

    # Provider trend
    provider_trend: dict[str, list[int]] = {}
    for i, t in enumerate(traces[-20:]):
        p = t.router_provider or "unknown"
        if p not in provider_trend:
            provider_trend[p] = [0] * 20
        provider_trend[p][i] = 1

    return {
        "window_size": len(traces),
        "latency": {
            "avg_ms": round(avg_latency, 2),
            "recent_avg_ms": round(recent_avg, 2),
            "direction": latency_direction,
        },
        "errors": {
            "rate": round(error_rate, 4),
            "trend": "stable" if error_rate < 0.1 else "increasing" if error_rate > 0.2 else "stable",
        },
        "provider_usage": {k: sum(v) for k, v in provider_trend.items()},
    }


@router.get("/insights")
async def analytics_insights(
    pipeline: Any = Depends(get_pipeline),
) -> dict[str, Any]:
    """Automated insights from the analytics data."""
    trace_store = getattr(pipeline, "_trace_store", None)
    traces = trace_store.list_traces(limit=100) if trace_store else []
    insights: list[dict[str, Any]] = []

    if not traces:
        return {"insights": [{"type": "info", "message": "Not enough data for insights yet."}], "count": 0}

    # Insight: high error rate
    error_rate = sum(1 for t in traces if t.errors) / len(traces)
    if error_rate > 0.2:
        insights.append({
            "type": "warning",
            "category": "reliability",
            "message": f"Error rate is {error_rate:.0%} — above the 20% threshold. Investigate recent failures.",
            "severity": "high",
        })

    # Insight: latency trend
    avg_latency = sum(t.total_latency_ms for t in traces) / len(traces)
    if avg_latency > 5000:
        insights.append({
            "type": "warning",
            "category": "performance",
            "message": f"Average latency is {avg_latency:.0f}ms — consider using a faster provider.",
            "severity": "medium",
        })

    # Insight: provider diversity
    providers = set(t.router_provider for t in traces if t.router_provider)
    if len(providers) == 1:
        insights.append({
            "type": "info",
            "category": "resilience",
            "message": "Only one provider is being used. Consider configuring alternatives for failover.",
            "severity": "low",
        })

    # Insight: memory usage
    memory_active = sum(1 for t in traces if t.memory_active)
    if memory_active < len(traces) * 0.5:
        insights.append({
            "type": "info",
            "category": "memory",
            "message": "Memory subsystem is active in less than 50% of requests. Consider enabling it for better context.",
            "severity": "low",
        })

    return {"insights": insights, "count": len(insights)}


@router.get("/subsystems/cross-metrics")
async def cross_subsystem_metrics(request: Request) -> dict[str, Any]:
    """Metrics that span multiple subsystems."""
    pipeline = getattr(request.app.state, "pipeline", None)
    trace_store = getattr(pipeline, "_trace_store", None) if pipeline else None
    traces = trace_store.list_traces(limit=50) if trace_store else []

    return {
        "pipeline_to_memory": {
            "traces_with_memory": sum(1 for t in traces if t.memory_active),
            "avg_memory_items": sum(t.memory_items_retrieved for t in traces) / max(1, len(traces)),
        },
        "pipeline_to_knowledge": {
            "traces_with_kg": sum(1 for t in traces if t.kg_active),
            "avg_kg_nodes": sum(t.kg_nodes_added for t in traces) / max(1, len(traces)),
        },
        "pipeline_to_learning": {
            "traces_with_learning": sum(1 for t in traces if t.learning_active),
        },
        "pipeline_to_reflection": {
            "traces_with_reflection": sum(1 for t in traces if t.reflection_active),
            "avg_reflection_score": sum(t.reflection_score for t in traces) / max(1, len(traces)),
        },
    }
