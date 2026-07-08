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


class MemoryMergeRequest(BaseModel):
    memory_ids: list[str] = Field(min_length=2)
    separator: str = "\n"


class MemorySummarizeRequest(BaseModel):
    memory_ids: list[str] = Field(min_length=1)
    max_length: int = 500


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


@router.get("/browse")
async def browse_memory(
    memory_type: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
    pinned_only: bool = False,
    pipeline=Depends(get_pipeline),
) -> dict[str, Any]:
    """Browse stored memories with pagination (M9.7).

    Unlike /search this does not update access statistics, so
    inspecting memory in the studio doesn't distort relevance scores.
    """
    mem = _get_memory_engine(pipeline)
    from memory.layer import MemoryType

    mt = None
    if memory_type:
        try:
            mt = MemoryType(memory_type)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"Unknown memory_type '{memory_type}'. "
                    f"Valid: {[t.value for t in MemoryType]}",
                    "code": "INVALID_MEMORY_TYPE",
                },
            ) from exc
    items = mem.browse(memory_type=mt, offset=offset, limit=limit, pinned_only=pinned_only)
    return {
        "items": [
            {
                "id": m.id,
                "content": str(m.content),
                "importance": m.importance,
                "memory_type": m.memory_type.value,
                "access_count": m.access_count,
                "pinned": mem.is_pinned(m.id),
                "metadata": dict(m.metadata),
            }
            for m in items
        ],
        "count": len(items),
        "offset": offset,
        "limit": limit,
    }


@router.post("/{memory_id}/pin")
async def pin_memory(memory_id: str, pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    """Pin a memory: exempt from pruning and limit-archiving (M9.7)."""
    mem = _get_memory_engine(pipeline)
    if not mem.pin(memory_id):
        raise HTTPException(
            status_code=404,
            detail={"message": f"Memory '{memory_id}' not found.", "code": "MEMORY_NOT_FOUND"},
        )
    return {"id": memory_id, "pinned": True}


@router.delete("/{memory_id}/pin")
async def unpin_memory(memory_id: str, pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    """Remove a pin (M9.7)."""
    mem = _get_memory_engine(pipeline)
    if not mem.unpin(memory_id):
        raise HTTPException(
            status_code=404,
            detail={"message": f"Memory '{memory_id}' is not pinned.", "code": "NOT_PINNED"},
        )
    return {"id": memory_id, "pinned": False}


@router.post("/merge")
async def merge_memories(
    body: MemoryMergeRequest, pipeline=Depends(get_pipeline)
) -> dict[str, Any]:
    """Merge multiple memories into one, deleting the sources (M9.7)."""
    mem = _get_memory_engine(pipeline)
    merged_id = mem.merge(body.memory_ids, separator=body.separator)
    if merged_id is None:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "At least two of the given memory ids must exist to merge.",
                "code": "MERGE_INSUFFICIENT_SOURCES",
            },
        )
    return {"id": merged_id, "status": "merged", "sources": body.memory_ids}


@router.post("/summarize")
async def summarize_memories(
    body: MemorySummarizeRequest, pipeline=Depends(get_pipeline)
) -> dict[str, Any]:
    """Summarize a set of memories (M9.7) — uses LongCat's summarizer."""
    mem = _get_memory_engine(pipeline)
    summary = mem.summarize_memories(body.memory_ids, max_length=body.max_length)
    return {"summary": summary, "memory_ids": body.memory_ids}


@router.post("/semantic-search")
async def semantic_search_memory(
    q: MemoryQuery, pipeline=Depends(get_pipeline)
) -> dict[str, Any]:
    """Semantic (index-backed) search with scores (M9.7)."""
    mem = _get_memory_engine(pipeline)
    results = mem.semantic_search(q.query, limit=q.count)
    return {
        "items": [
            {
                "id": m.id,
                "content": str(m.content),
                "importance": m.importance,
                "score": score,
            }
            for m, score in results
            if m.importance >= q.min_importance
        ],
        "query": q.query,
    }


@router.delete("/clear")
async def clear_memory(pipeline=Depends(get_pipeline)) -> dict[str, str]:
    """Clear all memory tiers (dev / testing)."""
    mem = _get_memory_engine(pipeline)
    try:
        mem.clear()
        return {"status": "cleared"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    """Permanently delete one memory (M9.7).

    Registered after /clear so the static route wins the match.
    """
    mem = _get_memory_engine(pipeline)
    if not mem.delete(memory_id):
        raise HTTPException(
            status_code=404,
            detail={"message": f"Memory '{memory_id}' not found.", "code": "MEMORY_NOT_FOUND"},
        )
    return {"id": memory_id, "status": "deleted"}

def _adaptive(request):
    manager = getattr(request.app.state, "adaptive_memory", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Adaptive memory manager not available")
    return manager


@router.get("/adaptive/status")
async def adaptive_status(request: Request) -> dict[str, Any]:
    """Adaptive memory policy + live counts (M9.21)."""
    return _adaptive(request).get_status()


@router.post("/adaptive/optimize")
async def adaptive_optimize(request: Request) -> dict[str, Any]:
    """Run one full evolution pass: consolidate → forget → compress.

    Returns real before/after memory counts (M9.21).
    """
    return _adaptive(request).optimize().to_dict()


@router.get("/adaptive/reports")
async def adaptive_reports(request: Request, limit: int = 20) -> dict[str, Any]:
    """Past evolution reports, newest first (M9.21)."""
    reports = _adaptive(request).get_reports(limit=limit)
    return {"reports": [r.to_dict() for r in reports], "count": len(reports)}
