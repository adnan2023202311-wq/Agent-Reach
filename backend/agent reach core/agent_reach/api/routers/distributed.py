"""
API layer: /api/v1/distributed — Distributed Agent Cloud (M10.1) +
Agent Swarm Intelligence (M10.2).

Layer: Interface/Presentation.

Exposes the NodeRegistry, RemoteDispatcher, and SwarmOrchestrator over
HTTP. Endpoints:

- GET    /nodes                — list cluster nodes
- POST   /nodes                — register a remote node
- DELETE /nodes/{node_id}      — deregister a node
- POST   /nodes/{node_id}/heartbeat — update a node's heartbeat
- GET    /nodes/stats          — cluster health stats
- POST   /execute              — execute a subtask on this node (remote dispatch target)
- POST   /swarm                — create and run a swarm
- GET    /swarm                — list recent swarms
- GET    /swarm/{swarm_id}     — get one swarm result
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from distributed import (
    NodeInfo,
    NodeStatus,
    SwarmRole,
    get_node_registry,
)
from domain.models import AgentType, SubTask, TaskStatus

router = APIRouter(prefix="/api/v1/distributed", tags=["distributed"])


# ── Node schemas ────────────────────────────────────────────────────────

class RegisterNodeRequest(BaseModel):
    hostname: str = ""
    endpoint: str = Field(..., description="e.g. http://10.0.0.5:8000")
    capabilities: list[str] = Field(default_factory=list)
    max_concurrent: int = 4
    metadata: dict[str, Any] = Field(default_factory=dict)


class HeartbeatRequest(BaseModel):
    load: Optional[int] = None
    status: Optional[str] = None


# ── Node endpoints ──────────────────────────────────────────────────────

@router.get("/nodes")
async def list_nodes(status: Optional[str] = None) -> dict[str, Any]:
    """List all cluster nodes, optionally filtered by status."""
    registry = get_node_registry()
    node_status = NodeStatus(status) if status else None
    nodes = registry.list_nodes(status=node_status)
    return {
        "nodes": [n.to_dict() for n in nodes],
        "count": len(nodes),
        "local_node_id": registry.local_node_id,
    }


@router.post("/nodes")
async def register_node(request: RegisterNodeRequest) -> dict[str, Any]:
    """Register a remote node in the cluster."""
    registry = get_node_registry()
    node = NodeInfo(
        hostname=request.hostname,
        endpoint=request.endpoint,
        capabilities=request.capabilities,
        max_concurrent=request.max_concurrent,
        metadata=request.metadata,
    )
    node_id = registry.register(node)
    return {"node_id": node_id, "status": "registered"}


@router.delete("/nodes/{node_id}")
async def deregister_node(node_id: str) -> dict[str, Any]:
    """Remove a node from the cluster."""
    registry = get_node_registry()
    if not registry.deregister(node_id):
        raise HTTPException(status_code=404, detail="Node not found or is local")
    return {"status": "deregistered", "node_id": node_id}


@router.post("/nodes/{node_id}/heartbeat")
async def heartbeat(node_id: str, request: HeartbeatRequest) -> dict[str, Any]:
    """Update a node's heartbeat."""
    registry = get_node_registry()
    if not registry.heartbeat(node_id, load=request.load):
        raise HTTPException(status_code=404, detail="Node not found")
    if request.status:
        node = registry.get(node_id)
        if node:
            node.status = NodeStatus(request.status)
    return {"status": "ok"}


@router.get("/nodes/stats")
async def cluster_stats() -> dict[str, Any]:
    """Aggregate cluster health."""
    return get_node_registry().cluster_stats()


# ── Remote execution endpoint ───────────────────────────────────────────

class RemoteExecuteRequest(BaseModel):
    """Sent by RemoteDispatcher to a remote node to execute a subtask."""
    subtask_id: str
    agent_type: str
    description: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


@router.post("/execute")
async def execute_remotely(
    request: RemoteExecuteRequest,
    pipeline: Any = None,
) -> dict[str, Any]:
    """Execute a subtask on this node (target of remote dispatch).

    This endpoint is called by RemoteDispatcher on a remote node. The
    subtask runs through this node's IntelligentPipeline.
    """
    # The pipeline is injected via app.state — see main.py wiring.
    # If not available, return an error so the caller falls back.
    if pipeline is None:
        # Fallback: try to get it from the request's app state.
        # FastAPI injects None when the dependency isn't wired; we
        # handle it gracefully.
        raise HTTPException(status_code=503, detail="Pipeline not available on this node")

    try:
        agent_type = AgentType(request.agent_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown agent type: {request.agent_type}")

    subtask = SubTask(
        id=request.subtask_id,
        description=request.description,
        agent_type=agent_type,
        input_data=request.input_data,
        depends_on=tuple(request.depends_on),
    )

    # Run through the pipeline's controller.
    try:
        outcome = await pipeline._controller.handle_request(request.description)
        succeeded = outcome.status == TaskStatus.SUCCEEDED
        output = outcome.results[0].output if outcome.results else None
        error = outcome.results[0].error if outcome.results and not succeeded else None
        return {
            "status": "succeeded" if succeeded else "failed",
            "output": output,
            "error": error,
        }
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


# ── Swarm endpoints ─────────────────────────────────────────────────────

class SwarmRoleSpec(BaseModel):
    role_name: str
    agent_type: str
    prompt_suffix: str = ""


class CreateSwarmRequest(BaseModel):
    objective: str
    roles: list[SwarmRoleSpec]


# The SwarmOrchestrator is lazily created on first use (it needs the
# dispatcher, which is on app.state). We store it as a module-level
# singleton keyed by the app's dispatcher to avoid recreating it.
_swarm_orchestrator = None


def _get_swarm_orchestrator(pipeline: Any):
    global _swarm_orchestrator
    if _swarm_orchestrator is None:
        from distributed import SwarmOrchestrator
        _swarm_orchestrator = SwarmOrchestrator(pipeline._controller._dispatcher)
    return _swarm_orchestrator


@router.post("/swarm")
async def create_swarm(
    request: CreateSwarmRequest,
    pipeline: Any = None,
) -> dict[str, Any]:
    """Create and run a swarm of agents on one objective."""
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not available")

    try:
        roles = [
            SwarmRole(
                role_name=r.role_name,
                agent_type=AgentType(r.agent_type),
                prompt_suffix=r.prompt_suffix,
            )
            for r in request.roles
        ]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    orchestrator = _get_swarm_orchestrator(pipeline)
    result = await orchestrator.run(request.objective, roles)
    return result.to_dict()


@router.get("/swarm")
async def list_swarms(limit: int = 20) -> dict[str, Any]:
    """List recent swarm executions."""
    # If the orchestrator hasn't been created yet, return empty.
    if _swarm_orchestrator is None:
        return {"swarms": [], "count": 0}
    swarms = _swarm_orchestrator.list_swarms(limit=limit)
    return {"swarms": swarms, "count": len(swarms)}


@router.get("/swarm/{swarm_id}")
async def get_swarm(swarm_id: str) -> dict[str, Any]:
    """Get one swarm result by ID."""
    if _swarm_orchestrator is None:
        raise HTTPException(status_code=404, detail="Swarm not found")
    result = _swarm_orchestrator.get_swarm(swarm_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Swarm not found")
    return result
