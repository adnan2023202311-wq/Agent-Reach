"""
API layer: /api/v1/cache — Intelligent Caching (M10.37).

Semantic cache and response reuse. Caches model responses by query
similarity (not just exact match) to reduce API calls and costs.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/cache", tags=["intelligent-cache"])


class CacheEntry(BaseModel):
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cache_key: str  # hash of the query
    query: str
    response: str
    provider: str = ""
    model: str = ""
    hit_count: int = 0
    created_at: float = Field(default_factory=time.time)
    last_hit: float = Field(default_factory=time.time)
    ttl_seconds: int = 3600
    tags: list[str] = Field(default_factory=list)


_cache: dict[str, CacheEntry] = {}
_key_to_entry: dict[str, str] = {}  # cache_key → entry_id


def _hash_query(query: str, provider: str = "", model: str = "") -> str:
    """Generate a cache key from the query + provider + model."""
    combined = f"{query.lower().strip()}|{provider}|{model}"
    return hashlib.sha256(combined.encode()).hexdigest()


class CacheStoreRequest(BaseModel):
    query: str
    response: str
    provider: str = ""
    model: str = ""
    ttl_seconds: int = 3600
    tags: list[str] = Field(default_factory=list)


@router.post("/store")
async def store_in_cache(request: CacheStoreRequest) -> dict[str, Any]:
    """Store a response in the cache."""
    key = _hash_query(request.query, request.provider, request.model)
    entry = CacheEntry(
        cache_key=key, query=request.query, response=request.response,
        provider=request.provider, model=request.model, ttl_seconds=request.ttl_seconds,
        tags=request.tags,
    )
    _cache[entry.entry_id] = entry
    _key_to_entry[key] = entry.entry_id
    return {"entry_id": entry.entry_id, "cache_key": key, "status": "cached"}


class CacheLookupRequest(BaseModel):
    query: str
    provider: str = ""
    model: str = ""


@router.post("/lookup")
async def lookup_cache(request: CacheLookupRequest) -> dict[str, Any]:
    """Look up a cached response by query (exact match)."""
    key = _hash_query(request.query, request.provider, request.model)
    entry_id = _key_to_entry.get(key)
    if entry_id is None:
        return {"found": False, "query": request.query[:200]}
    entry = _cache.get(entry_id)
    if entry is None:
        return {"found": False, "query": request.query[:200]}
    # Check TTL
    if time.time() - entry.created_at > entry.ttl_seconds:
        # Expired — remove
        _cache.pop(entry_id, None)
        _key_to_entry.pop(key, None)
        return {"found": False, "reason": "expired"}
    # Hit!
    entry.hit_count += 1
    entry.last_hit = time.time()
    return {"found": True, "entry_id": entry.entry_id, "response": entry.response, "hit_count": entry.hit_count}


@router.post("/lookup/semantic")
async def semantic_lookup(request: CacheLookupRequest, similarity_threshold: float = 0.7) -> dict[str, Any]:
    """Look up a cached response by semantic similarity (keyword overlap for now).

    In production, this would use vector embeddings for true semantic search.
    """
    query_words = set(request.query.lower().split())
    best_match: Optional[CacheEntry] = None
    best_score = 0.0
    for entry in _cache.values():
        # Check TTL first
        if time.time() - entry.created_at > entry.ttl_seconds:
            continue
        entry_words = set(entry.query.lower().split())
        if not query_words or not entry_words:
            continue
        overlap = len(query_words & entry_words)
        score = overlap / max(len(query_words), len(entry_words))
        if score > best_score and score >= similarity_threshold:
            best_score = score
            best_match = entry
    if best_match:
        best_match.hit_count += 1
        best_match.last_hit = time.time()
        return {"found": True, "similarity": round(best_score, 4), "response": best_match.response, "entry_id": best_match.entry_id}
    return {"found": False, "best_similarity": round(best_score, 4)}


@router.get("/entries")
async def list_cache_entries(limit: int = 20) -> dict[str, Any]:
    """List cache entries (sorted by hit count)."""
    entries = sorted(_cache.values(), key=lambda e: e.hit_count, reverse=True)
    return {"entries": [e.model_dump() for e in entries[:limit]], "count": len(entries)}


@router.delete("/entries/{entry_id}")
async def evict_entry(entry_id: str) -> dict[str, Any]:
    """Evict a single cache entry."""
    entry = _cache.pop(entry_id, None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Cache entry not found")
    _key_to_entry.pop(entry.cache_key, None)
    return {"status": "evicted"}


@router.post("/invalidate")
async def invalidate_by_tag(tag: str) -> dict[str, Any]:
    """Invalidate all cache entries with a specific tag."""
    evicted = 0
    to_remove = [eid for eid, e in _cache.items() if tag in e.tags]
    for eid in to_remove:
        entry = _cache.pop(eid, None)
        if entry:
            _key_to_entry.pop(entry.cache_key, None)
            evicted += 1
    return {"tag": tag, "evicted": evicted}


@router.post("/clear")
async def clear_cache() -> dict[str, Any]:
    """Clear the entire cache."""
    count = len(_cache)
    _cache.clear()
    _key_to_entry.clear()
    return {"status": "cleared", "entries_removed": count}


@router.get("/stats")
async def cache_stats() -> dict[str, Any]:
    total_entries = len(_cache)
    total_hits = sum(e.hit_count for e in _cache.values())
    total_size = sum(len(e.response) for e in _cache.values())
    avg_hits = total_hits / max(1, total_entries)
    return {
        "total_entries": total_entries,
        "total_hits": total_hits,
        "avg_hits_per_entry": round(avg_hits, 2),
        "estimated_size_kb": round(total_size / 1024, 2),
        "hit_rate": round(total_hits / max(1, total_hits + total_entries), 4),
    }
