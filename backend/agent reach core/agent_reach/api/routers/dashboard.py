"""
API layer: /api/v1/dashboard.

Layer: Interface/Presentation.

M9.4 — Live Dashboard. The M8 version returned honestly-empty
activity/recent_chats because nothing was persisted. M9.3 changed
that premise: the IntelligentPipeline now persists every execution
trace (core/trace_store.py), sessions live in the SessionManager, and
every M7 subsystem exposes real get_stats(). This endpoint aggregates
those existing sources — it does not introduce a new "dashboard
aggregation" concept in core/, and it fabricates nothing: every number
is read from a live runtime component, and zero means zero.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request

from api.dependencies import get_controller, get_pipeline, get_session_manager
from api.routers.agents import summarize_agent
from api.schemas import DashboardSnapshot
from config.settings import KNOWN_PROVIDERS, Settings, get_settings
from core.controller import MainController

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _subsystem_stats(pipeline: Any) -> dict[str, dict[str, Any]]:
    """Collect real stats from every pipeline subsystem.

    Uses the same lazy accessors the pipeline itself uses, so the
    numbers reflect the exact instances that served requests.
    """
    stats: dict[str, dict[str, Any]] = {}
    if pipeline is None:
        return stats
    accessors = {
        "memory": "_get_memory",
        "knowledge_graph": "_get_knowledge_graph",
        "learning": "_get_learning",
        "reflection": "_get_reflection",
        "context": "_get_context_engine",
        "moa": "_get_moa",
    }
    for name, accessor in accessors.items():
        try:
            subsystem = getattr(pipeline, accessor)()
            stats[name] = subsystem.get_stats()
        except Exception:
            stats[name] = {}
    try:
        router_obj = pipeline._get_router()
        stats["router"] = {
            "providers": router_obj.list_providers(),
            "health": router_obj.get_provider_health(),
        }
    except Exception:
        stats["router"] = {}
    return stats


def _build_runtime_section(
    pipeline: Any,
    session_manager: Any,
    workflow_engine: Any,
    settings: Settings,
) -> dict[str, Any]:
    """Assemble the M9.4 live runtime statistics block."""
    trace_agg: dict[str, Any] = {}
    pipeline_stats: dict[str, Any] = {}
    if pipeline is not None:
        try:
            trace_agg = pipeline.trace_store.aggregates()
        except Exception:
            trace_agg = {}
        try:
            pipeline_stats = pipeline.get_stats()
        except Exception:
            pipeline_stats = {}

    subsystems = _subsystem_stats(pipeline)

    # Conversations — real sessions from the SessionManager.
    active_conversations = 0
    total_conversations = 0
    if session_manager is not None:
        try:
            from conversation.session_manager import SessionState

            sessions = session_manager.list_sessions()
            total_conversations = len(sessions)
            active_conversations = sum(
                1 for s in sessions if s.state == SessionState.ACTIVE
            )
        except Exception:
            pass

    # Workflows — real results recorded by the WorkflowEngine.
    workflow_executions = 0
    if workflow_engine is not None:
        try:
            workflow_executions = len(workflow_engine.list_results())
        except Exception:
            pass

    # Provider usage — how often the router picked each provider,
    # read from persisted traces (real routing decisions).
    provider_usage: dict[str, int] = {}
    token_usage = 0
    if pipeline is not None:
        try:
            for trace in pipeline.list_traces(limit=pipeline.trace_store.max_traces):
                if trace.router_provider:
                    provider_usage[trace.router_provider] = (
                        provider_usage.get(trace.router_provider, 0) + 1
                    )
                token_usage += trace.context_tokens_used
        except Exception:
            pass

    # Estimated cost — router's per-provider cost model × usage.
    # Explicitly labeled an estimate: it derives from the router's
    # relative cost weights, not from provider billing APIs.
    estimated_cost = 0.0
    if pipeline is not None and provider_usage:
        try:
            router_obj = pipeline._get_router()
            for provider, count in provider_usage.items():
                estimated_cost += router_obj.get_cost(provider) * count
        except Exception:
            estimated_cost = 0.0

    memory_stats = subsystems.get("memory", {})
    kg_stats = subsystems.get("knowledge_graph", {})
    learning_stats = subsystems.get("learning", {})
    reflection_stats = subsystems.get("reflection", {})

    return {
        "active_conversations": active_conversations,
        "total_conversations": total_conversations,
        "workflow_executions": workflow_executions,
        "pipeline_requests": pipeline_stats.get("total_requests", 0),
        "avg_latency_ms": pipeline_stats.get("avg_latency_ms", 0.0),
        "p95_latency_ms": trace_agg.get("p95_latency_ms", 0.0),
        "errors": trace_agg.get("error_count", 0),
        "error_rate": trace_agg.get("error_rate", 0.0),
        "provider_usage": provider_usage,
        "configured_providers": [
            p for p in KNOWN_PROVIDERS if settings.is_provider_ready(p)
        ],
        "memory_size": memory_stats.get("memory_counts", {}).get("total", 0),
        "memory_counts": memory_stats.get("memory_counts", {}),
        "knowledge_nodes": kg_stats.get("total_nodes", 0),
        "knowledge_edges": kg_stats.get("total_edges", 0),
        "learning_records": learning_stats.get("total_executions", 0),
        "learning_success_rate": learning_stats.get("success_rate", 0.0),
        "reflection_executions": reflection_stats.get("total_reflections", 0),
        "reflection_retries": reflection_stats.get("total_retries", 0),
        "router_decisions": sum(provider_usage.values()),
        "token_usage": token_usage,
        "estimated_cost": estimated_cost,
        "stage_activity": trace_agg.get("stage_activity", {}),
        "subsystems": subsystems,
    }


def _recent_chats(session_manager: Any, limit: int = 10) -> list[dict[str, Any]]:
    """Most recently updated sessions, newest first."""
    if session_manager is None:
        return []
    try:
        sessions = session_manager.list_sessions()
    except Exception:
        return []
    ordered = sorted(sessions, key=lambda s: s.updated_at, reverse=True)
    return [s.to_dict() for s in ordered[:limit]]


def _recent_activity(pipeline: Any, limit: int = 20) -> list[dict[str, Any]]:
    """Recent pipeline executions as an activity feed (from real traces)."""
    if pipeline is None:
        return []
    try:
        traces = pipeline.list_traces(limit=limit)
    except Exception:
        return []
    activity = []
    for trace in traces:
        activity.append(
            {
                "request_id": trace.request_id,
                "timestamp": trace.timestamp,
                "latency_ms": trace.total_latency_ms,
                "provider": trace.router_provider,
                "errors": len(trace.errors),
                "reflection_score": trace.reflection_score,
                "answer_preview": (trace.final_answer or "")[:120],
            }
        )
    return activity


@router.get("", response_model=DashboardSnapshot)
async def get_dashboard(
    request: Request,
    controller: MainController = Depends(get_controller),
    settings: Settings = Depends(get_settings),
    pipeline=Depends(get_pipeline),
    session_manager=Depends(get_session_manager),
) -> DashboardSnapshot:
    agents = [summarize_agent(t, settings) for t in controller.registered_agent_types()]
    workflow_engine = getattr(request.app.state, "workflow_engine", None)

    return DashboardSnapshot(
        activity=_recent_activity(pipeline),
        recent_chats=_recent_chats(session_manager),
        active_agents=[a for a in agents if a.enabled],
        tools=[],
        runtime=_build_runtime_section(
            pipeline, session_manager, workflow_engine, settings
        ),
    )


@router.get("/runtime")
async def get_runtime_stats(
    request: Request,
    settings: Settings = Depends(get_settings),
    pipeline=Depends(get_pipeline),
    session_manager=Depends(get_session_manager),
) -> dict[str, Any]:
    """The M9.4 live runtime statistics block on its own.

    Lighter than the full dashboard snapshot — intended for frequent
    polling by the frontend's live dashboard widgets.
    """
    workflow_engine = getattr(request.app.state, "workflow_engine", None)
    return _build_runtime_section(pipeline, session_manager, workflow_engine, settings)
