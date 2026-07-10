"""
API layer: /api/v1/engineering-memory — Autonomous Engineering Memory (M10.27).

The platform learns from past engineering executions: which approaches
worked, which failed, what patterns emerge across projects. This
memory feeds back into future agent decisions.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/engineering-memory", tags=["engineering-memory"])


class EngineeringLesson(BaseModel):
    lesson_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: str = "general"  # architecture | testing | debugging | deployment | refactoring | performance
    title: str
    description: str = ""
    context: str = ""  # when this lesson applies
    outcome: str = ""  # positive | negative | neutral
    confidence: float = 0.5
    source_execution: str = ""  # trace request_id
    tags: list[str] = Field(default_factory=list)
    times_applied: int = 0
    times_validated: int = 0
    created_at: float = Field(default_factory=time.time)


class Pattern(BaseModel):
    pattern_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    pattern_type: str = "solution"  # solution | anti_pattern | trade_off
    description: str = ""
    when_to_use: str = ""
    when_not_to_use: str = ""
    examples: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    created_at: float = Field(default_factory=time.time)


_lessons: dict[str, EngineeringLesson] = {}
_patterns: dict[str, Pattern] = {}


class RecordLessonRequest(BaseModel):
    category: str = "general"
    title: str
    description: str = ""
    context: str = ""
    outcome: str = "neutral"
    confidence: float = 0.5
    source_execution: str = ""
    tags: list[str] = Field(default_factory=list)


@router.post("/lessons")
async def record_lesson(request: RecordLessonRequest) -> dict[str, Any]:
    """Record an engineering lesson learned from an execution."""
    lesson = EngineeringLesson(
        category=request.category, title=request.title, description=request.description,
        context=request.context, outcome=request.outcome, confidence=request.confidence,
        source_execution=request.source_execution, tags=request.tags,
    )
    _lessons[lesson.lesson_id] = lesson
    return {"lesson_id": lesson.lesson_id, "status": "recorded"}


@router.get("/lessons")
async def list_lessons(
    category: Optional[str] = None,
    outcome: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 50,
) -> dict[str, Any]:
    lessons = list(_lessons.values())
    if category:
        lessons = [l for l in lessons if l.category == category]
    if outcome:
        lessons = [l for l in lessons if l.outcome == outcome]
    if tag:
        lessons = [l for l in lessons if tag in l.tags]
    lessons.sort(key=lambda l: (l.confidence, l.times_validated), reverse=True)
    return {"lessons": [l.model_dump() for l in lessons[:limit]], "count": len(lessons)}


@router.get("/lessons/relevant")
async def relevant_lessons(context: str, limit: int = 5) -> dict[str, Any]:
    """Find lessons relevant to a given context (keyword match for now)."""
    context_lower = context.lower()
    scored = []
    for lesson in _lessons.values():
        score = 0
        for word in context_lower.split():
            if len(word) > 3 and word in lesson.title.lower():
                score += 2
            if len(word) > 3 and word in lesson.description.lower():
                score += 1
            if len(word) > 3 and word in lesson.context.lower():
                score += 3
        if score > 0:
            scored.append((score, lesson))
    scored.sort(key=lambda x: x[0], reverse=True)
    return {"context": context[:200], "lessons": [l.model_dump() for _, l in scored[:limit]], "count": len(scored)}


@router.post("/lessons/{lesson_id}/apply")
async def apply_lesson(lesson_id: str, was_valid: bool) -> dict[str, Any]:
    """Record that a lesson was applied and whether it was valid."""
    lesson = _lessons.get(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    lesson.times_applied += 1
    if was_valid:
        lesson.times_validated += 1
        lesson.confidence = min(1.0, lesson.confidence + 0.05)
    else:
        lesson.confidence = max(0.0, lesson.confidence - 0.1)
    return {"lesson_id": lesson_id, "confidence": lesson.confidence, "times_applied": lesson.times_applied}


class RecordPatternRequest(BaseModel):
    name: str
    pattern_type: str = "solution"
    description: str = ""
    when_to_use: str = ""
    when_not_to_use: str = ""
    examples: list[str] = Field(default_factory=list)


@router.post("/patterns")
async def record_pattern(request: RecordPatternRequest) -> dict[str, Any]:
    """Record a recurring engineering pattern."""
    pattern = Pattern(
        name=request.name, pattern_type=request.pattern_type, description=request.description,
        when_to_use=request.when_to_use, when_not_to_use=request.when_not_to_use, examples=request.examples,
    )
    _patterns[pattern.pattern_id] = pattern
    return {"pattern_id": pattern.pattern_id, "status": "recorded"}


@router.get("/patterns")
async def list_patterns(pattern_type: Optional[str] = None) -> dict[str, Any]:
    patterns = list(_patterns.values())
    if pattern_type:
        patterns = [p for p in patterns if p.pattern_type == pattern_type]
    return {"patterns": [p.model_dump() for p in patterns], "count": len(patterns)}


@router.get("/stats")
async def engineering_memory_stats() -> dict[str, Any]:
    from collections import Counter
    category_counts = Counter(l.category for l in _lessons.values())
    outcome_counts = Counter(l.outcome for l in _lessons.values())
    avg_confidence = sum(l.confidence for l in _lessons.values()) / max(1, len(_lessons))
    return {
        "total_lessons": len(_lessons),
        "total_patterns": len(_patterns),
        "lessons_by_category": dict(category_counts),
        "lessons_by_outcome": dict(outcome_counts),
        "avg_confidence": round(avg_confidence, 4),
        "most_validated": max(_lessons.values(), key=lambda l: l.times_validated).title if _lessons else "",
    }
