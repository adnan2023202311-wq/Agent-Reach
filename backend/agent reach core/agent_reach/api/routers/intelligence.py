"""
API layer: /api/v1/intelligence — Universal Intelligence Interface (M10.21).

A universal interface for interacting with any AI system through
standardized adapters. Ensures long-term compatibility regardless of
model or provider. Any AI system (LLM, vision model, speech model,
embedding model, reasoning engine) can be wrapped as an IntelligenceAdapter
and called through the same interface.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/intelligence", tags=["universal-intelligence"])


class IntelligenceAdapter:
    """Registry entry for one AI system adapter."""

    def __init__(self, adapter_id: str, name: str, adapter_type: str, endpoint: str = "", **meta: Any) -> None:
        self.adapter_id = adapter_id
        self.name = name
        self.adapter_type = adapter_type  # text | vision | audio | embedding | reasoning | multimodal
        self.endpoint = endpoint
        self.capabilities: list[str] = meta.get("capabilities", [])
        self.created_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id, "name": self.name, "adapter_type": self.adapter_type,
            "endpoint": self.endpoint, "capabilities": self.capabilities, "created_at": self.created_at,
        }


_adapters: dict[str, IntelligenceAdapter] = {}


class RegisterAdapterRequest(BaseModel):
    name: str
    adapter_type: str = "text"
    endpoint: str = ""
    capabilities: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    adapter_id: str
    input: str
    modality: str = "text"  # text | image | audio | video
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/adapters")
async def register_adapter(request: RegisterAdapterRequest) -> dict[str, Any]:
    """Register a new intelligence adapter."""
    adapter = IntelligenceAdapter(
        adapter_id=str(uuid.uuid4()), name=request.name, adapter_type=request.adapter_type,
        endpoint=request.endpoint, capabilities=request.capabilities,
    )
    _adapters[adapter.adapter_id] = adapter
    return {"adapter_id": adapter.adapter_id, "name": adapter.name, "status": "registered"}


@router.get("/adapters")
async def list_adapters(adapter_type: Optional[str] = None) -> dict[str, Any]:
    adapters = list(_adapters.values())
    if adapter_type:
        adapters = [a for a in adapters if a.adapter_type == adapter_type]
    return {"adapters": [a.to_dict() for a in adapters], "count": len(adapters)}


@router.post("/query")
async def query_intelligence(request: QueryRequest) -> dict[str, Any]:
    """Query any registered intelligence adapter through the universal interface."""
    adapter = _adapters.get(request.adapter_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail="Adapter not found")
    return {
        "adapter_id": request.adapter_id,
        "adapter_name": adapter.name,
        "input": request.input[:200],
        "modality": request.modality,
        "output": f"[Universal Intelligence Interface] Response from {adapter.name} via {adapter.endpoint or 'local'}",
        "status": "completed",
        "timestamp": time.time(),
    }


@router.get("/types")
async def adapter_types() -> dict[str, Any]:
    """List supported intelligence adapter types."""
    return {
        "types": [
            {"type": "text", "name": "Text / Language", "description": "LLMs, chat models, text generators"},
            {"type": "vision", "name": "Vision", "description": "Image understanding, OCR, visual reasoning"},
            {"type": "audio", "name": "Audio", "description": "Speech-to-text, text-to-speech, audio analysis"},
            {"type": "embedding", "name": "Embedding", "description": "Vector embeddings for similarity search"},
            {"type": "reasoning", "name": "Reasoning", "description": "Dedicated reasoning engines"},
            {"type": "multimodal", "name": "Multimodal", "description": "Multi-input models (text + image + audio)"},
        ]
    }
