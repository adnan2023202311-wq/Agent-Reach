"""
API layer: /api/v1/agents/global — Global Agent Registry (M10.3).

Exposes the GlobalAgentRegistry over HTTP for agent discovery,
versioning, trust scoring, and verification.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agents.global_registry import (
    AgentTrustScore,
    GlobalAgentEntry,
    get_global_agent_registry,
)

router = APIRouter(prefix="/api/v1/agents/global", tags=["global-agent-registry"])


class RegisterAgentRequest(BaseModel):
    agent_id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    homepage: str = ""
    category: str = "general"
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    min_platform_version: str = "10.0.0"


class RateAgentRequest(BaseModel):
    stars: float = Field(..., ge=0, le=5)


class RecordExecutionRequest(BaseModel):
    succeeded: bool
    latency_ms: float = 0.0


@router.get("")
async def discover_agents(
    query: str = "",
    category: Optional[str] = None,
    tag: Optional[str] = None,
    capability: Optional[str] = None,
    min_trust: float = 0.0,
    verified_only: bool = False,
    limit: int = Query(50, le=200),
) -> dict[str, Any]:
    """Discover agents by query, category, tag, capability, or trust."""
    registry = get_global_agent_registry()
    entries = registry.discover(
        query=query,
        category=category,
        tag=tag,
        capability=capability,
        min_trust=min_trust,
        verified_only=verified_only,
        limit=limit,
    )
    return {
        "agents": [e.to_dict() for e in entries],
        "count": len(entries),
    }


@router.post("")
async def register_agent(request: RegisterAgentRequest) -> dict[str, Any]:
    """Register a new agent (or a new version of an existing one)."""
    registry = get_global_agent_registry()
    entry = GlobalAgentEntry(
        agent_id=request.agent_id,
        name=request.name,
        version=request.version,
        description=request.description,
        author=request.author,
        homepage=request.homepage,
        category=request.category,
        tags=request.tags,
        capabilities=request.capabilities,
        dependencies=request.dependencies,
        min_platform_version=request.min_platform_version,
    )
    registry.register(entry)
    return {"status": "registered", "agent_id": entry.agent_id, "version": entry.version}


@router.get("/{agent_id}/latest")
async def get_latest_version(
    agent_id: str,
    platform_version: Optional[str] = None,
) -> dict[str, Any]:
    """Get the latest compatible version of an agent."""
    registry = get_global_agent_registry()
    entry = registry.get_latest(agent_id, platform_version)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No compatible version for agent '{agent_id}'")
    return entry.to_dict()


@router.get("/{agent_id}/{version}")
async def get_agent_version(agent_id: str, version: str) -> dict[str, Any]:
    """Get a specific version of an agent."""
    registry = get_global_agent_registry()
    entry = registry.get(agent_id, version)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' v{version} not found")
    return entry.to_dict()


@router.post("/{agent_id}/{version}/execute")
async def record_execution(
    agent_id: str,
    version: str,
    request: RecordExecutionRequest,
) -> dict[str, Any]:
    """Record an execution outcome (updates trust metrics)."""
    registry = get_global_agent_registry()
    entry = registry.get(agent_id, version)
    if entry is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    registry.record_execution(agent_id, version, request.succeeded, request.latency_ms)
    return {"status": "recorded", "trust": entry.trust.to_dict()}


@router.post("/{agent_id}/{version}/rate")
async def rate_agent(
    agent_id: str,
    version: str,
    request: RateAgentRequest,
) -> dict[str, Any]:
    """Rate an agent (0–5 stars)."""
    registry = get_global_agent_registry()
    entry = registry.get(agent_id, version)
    if entry is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    registry.rate(agent_id, version, request.stars)
    return {"status": "rated", "community_rating": entry.trust.community_rating}


@router.post("/{agent_id}/{version}/verify")
async def verify_agent(agent_id: str, version: str) -> dict[str, Any]:
    """Mark an agent as verified."""
    registry = get_global_agent_registry()
    if not registry.verify(agent_id, version):
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "verified"}


@router.get("/stats/summary")
async def registry_stats() -> dict[str, Any]:
    """Aggregate registry statistics."""
    return get_global_agent_registry().stats()
