"""
API layer: /api/v1/studio/agents — Agent Studio (M9.9).

Layer: Interface/Presentation.

M9.9 replaces the M8 mock (fabricated test outputs, fake latency)
with the real AgentStudio runtime (agents/studio.py): saved agents
are versioned, runs execute through the shared IntelligentPipeline,
and every run record carries the request_id of its persisted trace so
the Observatory can show the full execution breakdown ("Observe" and
"Debug" in the M9.9 workflow).

The M8 draft/publish/list surface is preserved for the frontend:
- POST /draft         → save (create or new version)
- POST /{id}/test     → real pipeline run (was mock output)
- POST /{id}/publish  → publish flag on the stored definition
- GET  ""             → catalog (native agents) + studio agents
"""

from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/studio/agents", tags=["agent-studio"])


class AgentDraft(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    tools: List[str] = Field(default_factory=list)
    model_provider: str = "anthropic"
    model_id: str = ""
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1)
    memory_enabled: bool = True
    reasoning: str = "balanced"


class AgentTestRequest(BaseModel):
    prompt: str = Field(min_length=1)


def _studio(request: Request):
    studio = getattr(request.app.state, "agent_studio", None)
    if studio is None:
        raise HTTPException(status_code=503, detail="Agent Studio not available")
    return studio


def _require_agent(studio, agent_id: str):
    definition = studio.get(agent_id)
    if definition is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"Studio agent '{agent_id}' not found.",
                "code": "AGENT_NOT_FOUND",
            },
        )
    return definition


@router.post("/draft")
async def create_draft(draft: AgentDraft, request: Request) -> dict[str, Any]:
    """Create a studio agent, or save a new version of an existing one."""
    studio = _studio(request)
    try:
        definition = studio.save(
            draft.name,
            description=draft.description,
            system_prompt=draft.system_prompt,
            tools=draft.tools,
            model_provider=draft.model_provider,
            model_id=draft.model_id,
            temperature=draft.temperature,
            max_tokens=draft.max_tokens,
            memory_enabled=draft.memory_enabled,
            reasoning=draft.reasoning,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "code": "INVALID_AGENT"},
        ) from exc
    return {"id": definition.agent_id, "status": "draft", "version": definition.version}


@router.get("")
async def list_studio_agents(request: Request) -> dict[str, Any]:
    """Native agent catalog + studio agents (drafts and published)."""
    studio = _studio(request)
    catalog = []
    try:
        from api.routers.agents import _METADATA

        for agent_type, meta in _METADATA.items():
            catalog.append(
                {
                    "id": agent_type.value,
                    "name": meta["name"],
                    "description": meta["description"],
                    "status": meta["status"],
                    "published": True,
                    "source": "native",
                }
            )
    except Exception:
        pass
    studio_agents = [
        {**a.to_dict(), "source": "studio"} for a in studio.list_agents()
    ]
    return {
        "catalog": catalog,
        "drafts": [a for a in studio_agents if not a["published"]],
        "published": [a for a in studio_agents if a["published"]],
    }


@router.get("/{agent_id}")
async def get_studio_agent(agent_id: str, request: Request) -> dict[str, Any]:
    """One studio agent's definition, metrics, and recent runs."""
    studio = _studio(request)
    definition = _require_agent(studio, agent_id)
    return {
        **definition.to_dict(),
        "metrics": studio.get_metrics(agent_id),
        "recent_runs": [r.to_dict() for r in studio.get_history(agent_id, limit=10)],
    }


@router.get("/{agent_id}/versions")
async def get_agent_versions(agent_id: str, request: Request) -> dict[str, Any]:
    """Version history: prior revisions + current (M9.9 'Improve')."""
    studio = _studio(request)
    definition = _require_agent(studio, agent_id)
    return {
        "agent_id": agent_id,
        "current": definition.to_dict(),
        "history": studio.get_versions(agent_id),
        "versions": definition.version,
    }


@router.get("/{agent_id}/runs")
async def get_agent_runs(
    agent_id: str, request: Request, limit: int = 50
) -> dict[str, Any]:
    """Real execution history for one studio agent (M9.9 'Observe')."""
    studio = _studio(request)
    _require_agent(studio, agent_id)
    records = studio.get_history(agent_id, limit=limit)
    return {
        "agent_id": agent_id,
        "runs": [r.to_dict() for r in records],
        "count": len(records),
        "metrics": studio.get_metrics(agent_id),
    }


@router.post("/{agent_id}/test")
async def test_agent(
    agent_id: str, body: AgentTestRequest, request: Request
) -> dict[str, Any]:
    """Run a studio agent through the REAL intelligent pipeline.

    The response's request_id links to the persisted execution trace
    (GET /api/v1/observatory/trace/{request_id}) for debugging.
    """
    studio = _studio(request)
    _require_agent(studio, agent_id)
    try:
        record = await studio.run(agent_id, body.prompt)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "code": "INVALID_PROMPT"},
        ) from exc
    return record.to_dict()


@router.post("/{agent_id}/publish")
async def publish_agent(agent_id: str, request: Request) -> dict[str, Any]:
    """Publish a studio agent. 404 for unknown ids — no fake success."""
    studio = _studio(request)
    _require_agent(studio, agent_id)
    definition = studio.publish(agent_id)
    return {
        "agent_id": agent_id,
        "status": "published",
        "version": definition.version,
    }


@router.delete("/{agent_id}")
async def delete_studio_agent(agent_id: str, request: Request) -> dict[str, Any]:
    """Delete a studio agent and its versions/history."""
    studio = _studio(request)
    if not studio.delete(agent_id):
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"Studio agent '{agent_id}' not found.",
                "code": "AGENT_NOT_FOUND",
            },
        )
    return {"agent_id": agent_id, "status": "deleted"}
