"""
API layer: /api/v1/memory/v2 — Memory V2 (M10.25).

Tiered memory with importance decay, episodic/semantic/procedural
memory types, and intelligent consolidation. Extends the existing
M7.1 LongCat memory engine without replacing it.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/memory/v2", tags=["memory-v2"])


class MemoryType:
    EPISODIC = "episodic"      # specific events / conversations
    SEMANTIC = "semantic"      # facts / knowledge
    PROCEDURAL = "procedural"  # how-to / skills
    WORKING = "working"        # short-term active context


class MemoryTier:
    HOT = "hot"        # always in RAM, instant access
    WARM = "warm"      # cached, fast access
    COLD = "cold"      # persisted, slower access
    ARCHIVED = "archived"  # compressed, on-demand retrieval


class MemoryItem(BaseModel):
    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    memory_type: str = MemoryType.EPISODIC
    tier: str = MemoryTier.WARM
    content: str
    importance: float = Field(0.5, ge=0.0, le=1.0)
    decay_rate: float = 0.01  # importance decay per hour
    tags: list[str] = Field(default_factory=list)
    source: str = ""  # what created this memory
    session_id: str = ""
    created_at: float = Field(default_factory=time.time)
    last_accessed: float = Field(default_factory=time.time)
    access_count: int = 0
    consolidated: bool = False


_memories: dict[str, MemoryItem] = {}


class StoreMemoryRequest(BaseModel):
    content: str
    memory_type: str = MemoryType.EPISODIC
    importance: float = 0.5
    tags: list[str] = Field(default_factory=list)
    source: str = ""
    session_id: str = ""


@router.post("/store")
async def store_memory(request: StoreMemoryRequest) -> dict[str, Any]:
    """Store a new memory item."""
    # Auto-assign tier based on importance
    if request.importance >= 0.8:
        tier = MemoryTier.HOT
    elif request.importance >= 0.3:
        tier = MemoryTier.WARM
    else:
        tier = MemoryTier.COLD
    item = MemoryItem(
        content=request.content, memory_type=request.memory_type, tier=tier,
        importance=request.importance, tags=request.tags, source=request.source,
        session_id=request.session_id,
    )
    _memories[item.item_id] = item
    return {"item_id": item.item_id, "tier": item.tier, "status": "stored"}


@router.get("/items")
async def list_memories(
    memory_type: Optional[str] = None,
    tier: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 50,
) -> dict[str, Any]:
    items = list(_memories.values())
    if memory_type:
        items = [i for i in items if i.memory_type == memory_type]
    if tier:
        items = [i for i in items if i.tier == tier]
    if tag:
        items = [i for i in items if tag in i.tags]
    items.sort(key=lambda i: i.importance, reverse=True)
    return {"items": [i.model_dump() for i in items[:limit]], "count": len(items)}


@router.get("/items/{item_id}")
async def get_memory(item_id: str) -> dict[str, Any]:
    item = _memories.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    item.last_accessed = time.time()
    item.access_count += 1
    return item.model_dump()


@router.get("/search")
async def search_memories(query: str, memory_type: Optional[str] = None, limit: int = 10) -> dict[str, Any]:
    """Search memories by content (keyword match for now; semantic search in production)."""
    query_lower = query.lower()
    items = [i for i in _memories.values() if query_lower in i.content.lower()]
    if memory_type:
        items = [i for i in items if i.memory_type == memory_type]
    items.sort(key=lambda i: (i.importance, i.access_count), reverse=True)
    results = []
    for item in items[:limit]:
        item.last_accessed = time.time()
        item.access_count += 1
        results.append(item.model_dump())
    return {"query": query, "results": results, "count": len(results)}


@router.post("/decay")
async def apply_decay() -> dict[str, Any]:
    """Apply importance decay to all memories (run periodically)."""
    now = time.time()
    decayed = 0
    demoted = 0
    for item in _memories.values():
        hours_elapsed = (now - item.last_accessed) / 3600.0
        item.importance = max(0.0, item.importance - (item.decay_rate * hours_elapsed))
        decayed += 1
        # Auto-demote tier based on decayed importance
        if item.importance < 0.1 and item.tier != MemoryTier.ARCHIVED:
            item.tier = MemoryTier.ARCHIVED
            demoted += 1
        elif item.importance < 0.3 and item.tier == MemoryTier.HOT:
            item.tier = MemoryTier.WARM
            demoted += 1
    return {"decayed": decayed, "demoted": demoted, "timestamp": now}


@router.post("/consolidate")
async def consolidate_memories() -> dict[str, Any]:
    """Consolidate episodic memories into semantic memories (like sleep)."""
    episodic = [i for i in _memories.values() if i.memory_type == MemoryType.EPISODIC and not i.consolidated]
    consolidated = 0
    for item in episodic:
        item.consolidated = True
        # Create a semantic summary (in production, use an LLM)
        semantic = MemoryItem(
            memory_type=MemoryType.SEMANTIC, tier=MemoryTier.WARM,
            content=f"[Consolidated] {item.content[:100]}",
            importance=item.importance * 0.8,  # slight decay during consolidation
            tags=item.tags + ["consolidated"], source="consolidation",
        )
        _memories[semantic.item_id] = semantic
        consolidated += 1
    return {"consolidated": consolidated, "total_episodic": len(episodic)}


@router.delete("/items/{item_id}")
async def delete_memory(item_id: str) -> dict[str, Any]:
    if _memories.pop(item_id, None) is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "deleted"}


@router.get("/stats")
async def memory_stats() -> dict[str, Any]:
    from collections import Counter
    type_counts = Counter(i.memory_type for i in _memories.values())
    tier_counts = Counter(i.tier for i in _memories.values())
    avg_importance = sum(i.importance for i in _memories.values()) / max(1, len(_memories))
    return {
        "total_memories": len(_memories),
        "by_type": dict(type_counts),
        "by_tier": dict(tier_counts),
        "avg_importance": round(avg_importance, 4),
        "consolidated": sum(1 for i in _memories.values() if i.consolidated),
    }
