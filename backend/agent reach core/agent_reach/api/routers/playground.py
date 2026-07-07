"""
API layer: /api/v1/playground — Model Playground (M8.10)
"""

from __future__ import annotations
from typing import Any, List
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from api.dependencies import get_pipeline

router = APIRouter(prefix="/api/v1/playground", tags=["playground"])

class CompareRequest(BaseModel):
    prompt: str
    providers: List[str]
    max_tokens: int = 512

@router.post("/compare")
async def compare_models(req: CompareRequest, pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    results = []
    for i, prov in enumerate(req.providers):
        # mock latency/cost for UI – real MOA would run parallel
        results.append({
            "provider": prov,
            "output": f"[{prov}] {req.prompt[:80]}... (M8 playground stub)",
            "tokens": len(req.prompt)//4,
            "latency_ms": 400 + i*120,
            "cost_usd": round(0.0015 * (i+1), 6),
            "quality_score": round(0.85 - i*0.05, 2),
        })
    return {"prompt": req.prompt, "results": results, "winner": results[0]["provider"] if results else None}

@router.get("/models")
async def playground_models() -> dict[str, Any]:
    return {
        "providers": [
            {"id": "anthropic", "models": ["claude-opus-4", "claude-sonnet-4", "claude-haiku-4"]},
            {"id": "openai", "models": ["gpt-5", "gpt-4o", "o4-mini"]},
            {"id": "google", "models": ["gemini-2.5-pro", "gemini-2.5-flash"]},
            {"id": "openrouter", "models": ["auto"]},
            {"id": "ollama", "models": ["llama3", "mistral", "qwen2"]},
        ]
    }
