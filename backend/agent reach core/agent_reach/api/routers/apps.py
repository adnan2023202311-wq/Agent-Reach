"""
API layer: /api/v1/apps — AI Application Builder (M10.8).

Allows users to create AI applications without writing code: assistants,
chatbots, research systems, automation systems, knowledge assistants.
Apps are defined by a config (name, type, system prompt, tools, model)
and deployed with one click — they run through the existing
IntelligentPipeline with app-specific configuration.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/apps", tags=["ai-app-builder"])


class AIApp(BaseModel):
    app_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    app_type: str  # assistant | chatbot | research | automation | knowledge
    description: str = ""
    system_prompt: str = ""
    provider_id: Optional[str] = None
    model_id: Optional[str] = None
    tools: list[str] = Field(default_factory=list)
    knowledge_base: Optional[str] = None
    deployed: bool = False
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class CreateAppRequest(BaseModel):
    name: str
    app_type: str = "assistant"
    description: str = ""
    system_prompt: str = ""
    provider_id: Optional[str] = None
    model_id: Optional[str] = None
    tools: list[str] = Field(default_factory=list)


class RunAppRequest(BaseModel):
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


_apps: dict[str, AIApp] = {}


@router.post("")
async def create_app(request: CreateAppRequest) -> dict[str, Any]:
    """Create a new AI application (one-click deploy)."""
    app = AIApp(
        name=request.name,
        app_type=request.app_type,
        description=request.description,
        system_prompt=request.system_prompt,
        provider_id=request.provider_id,
        model_id=request.model_id,
        tools=request.tools,
    )
    _apps[app.app_id] = app
    return {"app_id": app.app_id, "name": app.name, "app_type": app.app_type, "status": "created"}


@router.get("")
async def list_apps(app_type: Optional[str] = None) -> dict[str, Any]:
    apps = list(_apps.values())
    if app_type:
        apps = [a for a in apps if a.app_type == app_type]
    return {"apps": [a.model_dump() for a in apps], "count": len(apps)}


@router.get("/{app_id}")
async def get_app(app_id: str) -> dict[str, Any]:
    app = _apps.get(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    return app.model_dump()


@router.post("/{app_id}/deploy")
async def deploy_app(app_id: str) -> dict[str, Any]:
    """Deploy an app (marks it as live)."""
    app = _apps.get(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    app.deployed = True
    app.updated_at = time.time()
    return {"app_id": app_id, "deployed": True, "endpoint": f"/api/v1/apps/{app_id}/run"}


@router.post("/{app_id}/run")
async def run_app(
    app_id: str,
    request: RunAppRequest,
    pipeline: Any = None,
) -> dict[str, Any]:
    """Run an app — sends the message through the pipeline with the app's config."""
    app = _apps.get(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    if not app.deployed:
        raise HTTPException(status_code=403, detail="App is not deployed")
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not available")

    # Merge app config into the request context.
    context = {
        **request.context,
        "app_id": app_id,
        "app_type": app.app_type,
        "system_prompt": app.system_prompt,
    }
    if app.provider_id:
        context["provider_id"] = app.provider_id
    if app.model_id:
        context["model_id"] = app.model_id

    result = await pipeline.process(request.message, extra_context=context)
    return {
        "app_id": app_id,
        "answer": result.outcome.answer,
        "status": result.outcome.status.value,
        "trace": result.trace.to_dict(),
    }


@router.get("/templates/catalog")
async def app_templates() -> dict[str, Any]:
    """Return the catalog of app templates (no-code starting points)."""
    return {
        "templates": [
            {
                "template_id": "customer-support",
                "name": "Customer Support Assistant",
                "app_type": "assistant",
                "description": "A helpful support agent that answers customer questions",
                "system_prompt": "You are a customer support assistant. Be helpful, concise, and empathetic.",
                "suggested_tools": [],
            },
            {
                "template_id": "research-analyst",
                "name": "Research Analyst",
                "app_type": "research",
                "description": "An agent that researches topics and produces structured reports",
                "system_prompt": "You are a research analyst. Provide thorough, well-cited analysis.",
                "suggested_tools": [],
            },
            {
                "template_id": "knowledge-base",
                "name": "Knowledge Base Assistant",
                "app_type": "knowledge",
                "description": "An assistant that answers questions from a knowledge base",
                "system_prompt": "You are a knowledge base assistant. Answer from the provided knowledge.",
                "suggested_tools": [],
            },
            {
                "template_id": "automation-bot",
                "name": "Automation Bot",
                "app_type": "automation",
                "description": "A bot that executes automated workflows",
                "system_prompt": "You are an automation bot. Execute tasks efficiently.",
                "suggested_tools": [],
            },
        ]
    }
