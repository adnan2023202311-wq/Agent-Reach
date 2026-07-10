"""
API layer: /api/v1/infrastructure — Autonomous Infrastructure Manager (M10.16).

Manages infrastructure automatically: scaling, recovery, deployment,
resource allocation, and optimization. Makes decisions based on cluster
health, load, and cost metrics.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/infrastructure", tags=["infra-manager"])


class ScalingPolicy(BaseModel):
    policy_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    metric: str = "cpu"  # cpu | memory | requests | latency
    scale_up_threshold: float = 80.0
    scale_down_threshold: float = 30.0
    min_nodes: int = 1
    max_nodes: int = 10
    enabled: bool = True


class Deployment(BaseModel):
    deployment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: str
    status: str = "pending"  # pending | in_progress | completed | failed | rolled_back
    nodes_affected: list[str] = Field(default_factory=list)
    started_at: float = Field(default_factory=time.time)
    completed_at: float = 0.0
    rollback_available: bool = True


class InfraAction(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action_type: str  # scale_up | scale_down | deploy | rollback | restart | drain
    target: str = ""
    status: str = "pending"  # pending | executing | completed | failed
    timestamp: float = Field(default_factory=time.time)
    details: dict[str, Any] = Field(default_factory=dict)


_policies: dict[str, ScalingPolicy] = {}
_deployments: dict[str, Deployment] = {}
_actions: list[InfraAction] = []


@router.get("/status")
async def infra_status() -> dict[str, Any]:
    """Current infrastructure status."""
    try:
        from distributed import get_node_registry
        node_stats = get_node_registry().cluster_stats()
    except Exception:
        node_stats = {}
    return {
        "cluster": node_stats,
        "active_deployments": sum(1 for d in _deployments.values() if d.status in ("pending", "in_progress")),
        "scaling_policies": len(_policies),
        "recent_actions": len(_actions),
        "timestamp": time.time(),
    }


@router.post("/scaling-policies")
async def create_scaling_policy(request: ScalingPolicy) -> dict[str, Any]:
    """Create a scaling policy."""
    _policies[request.policy_id] = request
    return {"policy_id": request.policy_id, "status": "created"}


@router.get("/scaling-policies")
async def list_scaling_policies() -> dict[str, Any]:
    return {"policies": [p.model_dump() for p in _policies.values()], "count": len(_policies)}


@router.post("/scale/{direction}")
async def scale_cluster(direction: str, target_count: Optional[int] = None) -> dict[str, Any]:
    """Scale the cluster up or down."""
    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="Direction must be 'up' or 'down'")
    action = InfraAction(
        action_type=f"scale_{direction}",
        details={"target_count": target_count, "direction": direction},
    )
    _actions.append(action)
    return {"action_id": action.action_id, "status": "initiated", "direction": direction}


@router.post("/deploy")
async def create_deployment(version: str, nodes: list[str] = None) -> dict[str, Any]:
    """Create a new deployment."""
    deployment = Deployment(version=version, nodes_affected=nodes or [])
    _deployments[deployment.deployment_id] = deployment
    return {"deployment_id": deployment.deployment_id, "version": version, "status": "pending"}


@router.post("/deploy/{deployment_id}/execute")
async def execute_deployment(deployment_id: str) -> dict[str, Any]:
    """Execute a deployment."""
    deployment = _deployments.get(deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    deployment.status = "in_progress"
    # Simulate deployment (in production, this would orchestrate real nodes)
    deployment.status = "completed"
    deployment.completed_at = time.time()
    return {"deployment_id": deployment_id, "status": "completed"}


@router.post("/deploy/{deployment_id}/rollback")
async def rollback_deployment(deployment_id: str) -> dict[str, Any]:
    """Rollback a deployment."""
    deployment = _deployments.get(deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if not deployment.rollback_available:
        raise HTTPException(status_code=400, detail="Rollback not available for this deployment")
    deployment.status = "rolled_back"
    return {"deployment_id": deployment_id, "status": "rolled_back"}


@router.get("/deployments")
async def list_deployments(limit: int = 20) -> dict[str, Any]:
    """List recent deployments."""
    deps = sorted(_deployments.values(), key=lambda d: d.started_at, reverse=True)
    return {"deployments": [d.model_dump() for d in deps[:limit]], "count": len(deps)}


@router.get("/actions")
async def list_actions(limit: int = 50) -> dict[str, Any]:
    """List recent infrastructure actions."""
    return {"actions": [a.model_dump() for a in _actions[-limit:]], "count": len(_actions)}


@router.post("/recover/{node_id}")
async def recover_node(node_id: str) -> dict[str, Any]:
    """Attempt to recover a failed node."""
    action = InfraAction(
        action_type="restart",
        target=node_id,
        details={"reason": "manual_recovery"},
    )
    _actions.append(action)
    return {"action_id": action.action_id, "node_id": node_id, "status": "recovery_initiated"}


@router.get("/recommendations")
async def infra_recommendations() -> dict[str, Any]:
    """Get infrastructure optimization recommendations."""
    recommendations: list[dict[str, Any]] = []
    try:
        from distributed import get_node_registry
        stats = get_node_registry().cluster_stats()
        if stats.get("utilization", 0) > 0.8:
            recommendations.append({
                "type": "scale_up",
                "priority": "high",
                "description": f"Cluster utilization is {stats['utilization']:.0%}. Consider scaling up.",
            })
        elif stats.get("utilization", 0) < 0.2 and stats.get("total_nodes", 0) > 1:
            recommendations.append({
                "type": "scale_down",
                "priority": "low",
                "description": f"Cluster utilization is only {stats['utilization']:.0%}. Consider scaling down to save costs.",
            })
        if stats.get("offline", 0) > 0:
            recommendations.append({
                "type": "recovery",
                "priority": "high",
                "description": f"{stats['offline']} node(s) are offline. Initiate recovery.",
            })
    except Exception:
        pass
    return {"recommendations": recommendations, "timestamp": time.time()}
