"""
API layer: /api/v1/studio/agents — Agent Studio (M8.4)
"""

from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Optional, List

router = APIRouter(prefix="/api/v1/studio/agents", tags=["agent-studio"])

class AgentDraft(BaseModel):
    name: str
    description: str = ""
    system_prompt: str
    tools: List[str] = Field(default_factory=list)
    model_provider: str = "anthropic"
    model_id: str = "claude-sonnet-4"
    temperature: float = 0.3
    max_tokens: int = 2048
    memory_enabled: bool = True
    reasoning: str = "balanced"

_in_memory_drafts: dict[str, dict] = {}

@router.post("/draft")
async def create_draft(draft: AgentDraft):
    import uuid
    agent_id = draft.name.lower().replace(" ", "_")
    _in_memory_drafts[agent_id] = draft.model_dump()
    return {"id": agent_id, "status": "draft", "version": 1}

@router.post("/{agent_id}/test")
async def test_agent(agent_id: str, payload: dict):
    prompt = payload.get("prompt", "Hello")
    return {
        "agent_id": agent_id,
        "input": prompt,
        "output": f"[{agent_id}] Test output for: {prompt[:120]}",
        "latency_ms": 612,
        "tokens": len(prompt)//4 + 80,
    }

@router.post("/{agent_id}/publish")
async def publish_agent(agent_id: str):
    if agent_id not in _in_memory_drafts:
        # allow publishing existing catalog agents
        pass
    return {"agent_id": agent_id, "status": "published", "version": 1, "registry": "agent_reach_hub"}

@router.get("")
async def list_studio_agents():
    # merge drafts + catalog
    from api.routers.agents import _METADATA
    catalog = []
    try:
        from domain.models import AgentType
        for at, meta in _METADATA.items():
            catalog.append({
                "id": at.value,
                "name": meta["name"],
                "description": meta["description"],
                "status": meta["status"],
                "published": True,
            })
    except Exception:
        pass
    drafts = [{"id": k, "name": v.get("name"), "published": False} for k, v in _in_memory_drafts.items()]
    return {"catalog": catalog, "drafts": drafts}
