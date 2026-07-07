"""
API layer: /api/v1/skills — Skill Ecosystem (M7.6 / M8)
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])

# try to load real Skill Engine
try:
    from skills.ecosystem import SkillRegistry  # type: ignore
    _SKILL_REGISTRY = SkillRegistry()
except Exception:
    _SKILL_REGISTRY = None

_FALLBACK = [
    {"id": "web_search", "name": "Web Search", "version": "1.2.0", "category": "research", "enabled": True},
    {"id": "code_analysis", "name": "Code Analysis", "version": "2.0.1", "category": "coding", "enabled": True},
    {"id": "data_extraction", "name": "Data Extraction", "version": "1.0.3", "category": "data", "enabled": True},
    {"id": "summarization", "name": "Summarization", "version": "1.5.0", "category": "nlp", "enabled": True},
]


class SkillExecuteRequest(BaseModel):
    input: dict[str, Any] = {}


@router.get("")
async def list_skills(category: str = "") -> dict[str, Any]:
    items = []
    if _SKILL_REGISTRY and hasattr(_SKILL_REGISTRY, "list"):
        try:
            skills = _SKILL_REGISTRY.list()  # type: ignore
            items = skills
        except Exception:
            items = _FALLBACK
    else:
        items = _FALLBACK
    if category:
        items = [s for s in items if s.get("category") == category]
    return {"items": items, "count": len(items)}


@router.get("/{skill_id}")
async def get_skill(skill_id: str) -> dict[str, Any]:
    items = _FALLBACK
    found = next((s for s in items if s["id"] == skill_id), None)
    if not found:
        raise HTTPException(status_code=404, detail="Skill not found")
    return found


@router.post("/{skill_id}/execute")
async def execute_skill(skill_id: str, req: SkillExecuteRequest) -> dict[str, Any]:
    # stub execution – real SkillEngine would run here
    return {
        "skill_id": skill_id,
        "input": req.input,
        "output": {"result": f"Skill {skill_id} executed (M8 stub)", "success": True},
        "latency_ms": 42,
        "status": "succeeded",
    }
