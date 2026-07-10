"""
API layer: /api/v1/reliability — Production Reliability (M10.31).

Health checks, circuit breakers, rate limiting, and SLA monitoring.
Ensures the platform stays available under load and degrades gracefully
when subsystems fail.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/reliability", tags=["production-reliability"])


class CircuitBreaker(BaseModel):
    breaker_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    state: str = "closed"  # closed | open | half_open
    failure_count: int = 0
    failure_threshold: int = 5
    recovery_timeout: float = 60.0  # seconds before half-open
    last_failure: float = 0.0
    last_state_change: float = Field(default_factory=time.time)


class HealthCheck(BaseModel):
    check_id: str
    name: str
    healthy: bool = True
    latency_ms: float = 0.0
    last_run: float = Field(default_factory=time.time)
    message: str = ""


class SLAMetric(BaseModel):
    metric_name: str
    target: float = 0.0
    actual: float = 0.0
    unit: str = ""
    status: str = "meeting"  # meeting | breaching | unknown


_breakers: dict[str, CircuitBreaker] = {}
_health_history: list[dict[str, Any]] = []
_sla_metrics: dict[str, SLAMetric] = {
    "uptime": SLAMetric(metric_name="uptime", target=99.9, unit="%"),
    "avg_response_time": SLAMetric(metric_name="avg_response_time", target=2000, unit="ms"),
    "error_rate": SLAMetric(metric_name="error_rate", target=1.0, unit="%"),
}


class CreateBreakerRequest(BaseModel):
    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 60.0


@router.post("/circuit-breakers")
async def create_breaker(request: CreateBreakerRequest) -> dict[str, Any]:
    """Create a circuit breaker for a service."""
    breaker = CircuitBreaker(
        name=request.name, failure_threshold=request.failure_threshold,
        recovery_timeout=request.recovery_timeout,
    )
    _breakers[breaker.breaker_id] = breaker
    return {"breaker_id": breaker.breaker_id, "name": breaker.name, "state": breaker.state}


@router.get("/circuit-breakers")
async def list_breakers() -> dict[str, Any]:
    return {"breakers": [b.model_dump() for b in _breakers.values()], "count": len(_breakers)}


@router.post("/circuit-breakers/{breaker_id}/record-success")
async def record_success(breaker_id: str) -> dict[str, Any]:
    """Record a successful call through the circuit breaker."""
    breaker = _breakers.get(breaker_id)
    if breaker is None:
        return {"error": "not found"}
    if breaker.state == "half_open":
        breaker.state = "closed"
        breaker.failure_count = 0
        breaker.last_state_change = time.time()
    return {"breaker_id": breaker_id, "state": breaker.state}


@router.post("/circuit-breakers/{breaker_id}/record-failure")
async def record_failure(breaker_id: str) -> dict[str, Any]:
    """Record a failed call through the circuit breaker."""
    breaker = _breakers.get(breaker_id)
    if breaker is None:
        return {"error": "not found"}
    breaker.failure_count += 1
    breaker.last_failure = time.time()
    if breaker.failure_count >= breaker.failure_threshold:
        breaker.state = "open"
        breaker.last_state_change = time.time()
    return {"breaker_id": breaker_id, "state": breaker.state, "failures": breaker.failure_count}


@router.post("/circuit-breakers/{breaker_id}/check")
async def check_breaker(breaker_id: str) -> dict[str, Any]:
    """Check if a request is allowed (circuit breaker state check)."""
    breaker = _breakers.get(breaker_id)
    if breaker is None:
        return {"allowed": True, "reason": "no_breaker"}
    # Auto-transition from open to half-open after recovery timeout
    if breaker.state == "open":
        if (time.time() - breaker.last_state_change) > breaker.recovery_timeout:
            breaker.state = "half_open"
            breaker.last_state_change = time.time()
    allowed = breaker.state != "open"
    return {"allowed": allowed, "state": breaker.state, "reason": "circuit_open" if not allowed else "ok"}


@router.get("/health", response_model=list[HealthCheck])
async def comprehensive_health(request: Request) -> list[HealthCheck]:
    """Run all health checks and return results."""
    checks: list[HealthCheck] = []
    # Pipeline health
    pipeline = getattr(request.app.state, "pipeline", None)
    checks.append(HealthCheck(check_id="pipeline", name="Intelligent Pipeline", healthy=pipeline is not None))
    # Controller
    controller = getattr(request.app.state, "controller", None)
    checks.append(HealthCheck(check_id="controller", name="Main Controller", healthy=controller is not None))
    # Conversation engine
    conv = getattr(request.app.state, "conversation_engine", None)
    checks.append(HealthCheck(check_id="conversation", name="Conversation Engine", healthy=conv is not None))
    # Tool runtime
    tr = getattr(request.app.state, "tool_runtime", None)
    checks.append(HealthCheck(check_id="tool_runtime", name="Tool Runtime", healthy=tr is not None))
    # Node registry
    try:
        from distributed import get_node_registry
        stats = get_node_registry().cluster_stats()
        checks.append(HealthCheck(check_id="cluster", name="Cluster Nodes",
                                  healthy=stats.get("online", 0) > 0,
                                  message=f"{stats['online']}/{stats['total_nodes']} nodes online"))
    except Exception:
        checks.append(HealthCheck(check_id="cluster", name="Cluster Nodes", healthy=False, message="unavailable"))
    # Record in history
    _health_history.append({"timestamp": time.time(), "checks": [c.model_dump() for c in checks]})
    if len(_health_history) > 100:
        _health_history[:] = _health_history[-50:]
    return checks


@router.get("/sla")
async def sla_dashboard() -> dict[str, Any]:
    """SLA monitoring dashboard."""
    # In production, these would be computed from real metrics
    _sla_metrics["uptime"].actual = 99.95
    _sla_metrics["avg_response_time"].actual = 850
    _sla_metrics["error_rate"].actual = 0.3
    for m in _sla_metrics.values():
        if m.metric_name == "uptime":
            m.status = "meeting" if m.actual >= m.target else "breaching"
        elif m.metric_name == "avg_response_time":
            m.status = "meeting" if m.actual <= m.target else "breaching"
        elif m.metric_name == "error_rate":
            m.status = "meeting" if m.actual <= m.target else "breaching"
    return {"metrics": [m.model_dump() for m in _sla_metrics.values()], "timestamp": time.time()}


@router.get("/health/history")
async def health_history(limit: int = 20) -> dict[str, Any]:
    """Historical health check results."""
    return {"history": _health_history[-limit:], "count": len(_health_history)}
