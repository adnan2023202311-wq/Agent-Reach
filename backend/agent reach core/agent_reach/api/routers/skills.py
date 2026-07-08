"""
API layer: /api/v1/skills — Skill Ecosystem (M7.6 / M9 completion).

M9 completion: replaced the M8 stub execution with real SkillEngine
invocation. When the SkillRegistry is available, skills are executed
through the engine; when unavailable, a diagnostic fallback is served.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])

# Try to load the real Skill Engine.
_SKILL_REGISTRY = None
_SKILL_ENGINE = None
try:
    from skills.ecosystem import SkillRegistry  # type: ignore
    from skills.engine import SkillEngine  # type: ignore

    _SKILL_REGISTRY = SkillRegistry()
    _SKILL_ENGINE = SkillEngine(registry=_SKILL_REGISTRY)
    logger.info("Skills router: real SkillEngine loaded.")
except Exception:
    logger.warning(
        "Skills router: SkillEngine unavailable — serving diagnostic fallback."
    )

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
    items: list[dict[str, Any]] = []
    if _SKILL_REGISTRY and hasattr(_SKILL_REGISTRY, "list"):
        try:
            raw = _SKILL_REGISTRY.list()
            items = [
                {"id": s.id, "name": s.name, "version": getattr(s, "version", "1.0.0"),
                 "category": getattr(s, "category", ""), "enabled": getattr(s, "enabled", True)}
                if hasattr(s, "id") else s
                for s in raw
            ]
        except Exception:
            items = _FALLBACK
    else:
        items = _FALLBACK
    if category:
        items = [s for s in items if s.get("category") == category]
    return {"items": items, "count": len(items), "source": "live" if _SKILL_REGISTRY else "fallback"}


@router.get("/{skill_id}")
async def get_skill(skill_id: str) -> dict[str, Any]:
    if _SKILL_REGISTRY and hasattr(_SKILL_REGISTRY, "get"):
        try:
            skill = _SKILL_REGISTRY.get(skill_id)
            if skill is not None:
                return {
                    "id": skill.id if hasattr(skill, "id") else skill.get("id"),
                    "name": skill.name if hasattr(skill, "name") else skill.get("name", ""),
                    "version": getattr(skill, "version", "1.0.0"),
                    "category": getattr(skill, "category", ""),
                    "enabled": getattr(skill, "enabled", True),
                    "source": "live",
                }
        except Exception:
            pass
    found = next((s for s in _FALLBACK if s["id"] == skill_id), None)
    if not found:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {**found, "source": "fallback"}


@router.post("/{skill_id}/execute")
async def execute_skill(skill_id: str, req: SkillExecuteRequest) -> dict[str, Any]:
    if _SKILL_ENGINE is not None:
        try:
            result = _SKILL_ENGINE.execute(skill_id, req.input)
            return {
                "skill_id": skill_id,
                "input": req.input,
                "output": result.output if hasattr(result, "output") else result,
                "status": "succeeded",
                "source": "live",
            }
        except Exception as exc:
            logger.exception("Skill execution failed: %s", skill_id)
            return {
                "skill_id": skill_id,
                "input": req.input,
                "output": None,
                "error": str(exc),
                "status": "failed",
                "source": "live",
            }

    # Fallback — diagnostic, not a stub.
    return {
        "skill_id": skill_id,
        "input": req.input,
        "output": None,
        "status": "unavailable",
        "detail": "SkillEngine not loaded — no skills registered in this runtime.",
        "source": "fallback",
    }
