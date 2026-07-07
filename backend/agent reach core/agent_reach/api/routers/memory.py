"""
API layer: /api/v1/memory — LongCat Memory Engine access.

Layer: Interface/Presentation.

Milestone 8: exposes Memory Engine for the AI Workspace / Memory Studio.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.dependencies import get_pipeline

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


class MemoryItemIn(BaseModel):
    content: str
    importance: float = 0.5
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryQuery(BaseModel):
    query: str = ""
    count: int = 10
    min_importance: float = 0.0


def _get_memory_engine(pipeline):
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Intelligent pipeline not available")
    # lazy init via private accessor – same pattern as pipeline internals
    try:
        return pipeline._get_memory()  # type: ignore[attr-defined]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/stats")
async def get_memory_stats(pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    """Return LongCat memory statistics."""
    mem = _get_memory_engine(pipeline)
    try:
        stats = mem.get_stats()
    except Exception:
        stats = {}
    # enrich with pipeline-level counters
    return {
        "engine": "LongCat",
        "version": "7.1",
        **stats,
        "status": "ready",
    }


@router.post("/store")
async def store_memory(item: MemoryItemIn, pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    """Store an item in LongCat memory."""
    mem = _get_memory_engine(pipeline)
    try:
        mid = mem.store(
            content=item.content,
            importance=item.importance,
            metadata={**item.metadata, "tags": item.tags},
            add_to_working=True,
        )
        # mem.store returns id in some implementations, else generate
        return {"id": str(mid) if mid else "stored", "status": "stored"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/search")
async def search_memory(q: MemoryQuery, pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    """Semantic / relevance search over memory."""
    mem = _get_memory_engine(pipeline)
    try:
        results = mem.retrieve_relevant(count=q.count, query=q.query or None)
        items = []
        for r in results:
            # MemoryItem may be dataclass or dict-like
            content = getattr(r, "content", str(r))
            importance = getattr(r, "importance", 0.5)
            mid = getattr(r, "id", getattr(r, "memory_id", ""))
            items.append({"id": str(mid), "content": content, "importance": importance})
        # filter by min_importance
        items = [i for i in items if i["importance"] >= q.min_importance]
        return {"items": items, "count": len(items), "query": q.query}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/working")
async def get_working_memory(pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    """Return current working memory snapshot."""
    mem = _get_memory_engine(pipeline)
    try:
        working = list(getattr(mem, "working_memory", []))
        items = []
        for w in working:
            content = getattr(w, "content", str(w))
            items.append({"content": content})
        return {"items": items, "count": len(items)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/compress")
async def compress_memory(pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    """Trigger memory consolidation / compression."""
    mem = _get_memory_engine(pipeline)
    try:
        # LongCatMemoryEngine exposes consolidate() in M7
        if hasattr(mem, "consolidate"):
            result = mem.consolidate()  # type: ignore
        else:
            result = {"consolidated": 0}
        return {"status": "compressed", "result": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/clear")
async def clear_memory(pipeline=Depends(get_pipeline)) -> dict[str, str]:
    """Clear all memory tiers (dev / testing)."""
    mem = _get_memory_engine(pipeline)
    try:
        mem.clear()
        return {"status": "cleared"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
