"""
API layer: /api/v1/marketplace/v2 — Marketplace V2 (M10.9).

Expands the existing M9.22 PluginMarketplace to support all item types:
agents, plugins, skills, templates, memory packs, prompt packs,
workflows, knowledge packs.

Builds on marketplace/__init__.py's PluginMarketplace (does NOT replace
it). V2 adds a broader item type taxonomy and richer search.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/marketplace/v2", tags=["marketplace-v2"])


class MarketplaceItemType:
    AGENT = "agent"
    PLUGIN = "plugin"
    SKILL = "skill"
    TEMPLATE = "template"
    MEMORY_PACK = "memory_pack"
    PROMPT_PACK = "prompt_pack"
    WORKFLOW = "workflow"
    KNOWLEDGE_PACK = "knowledge_pack"


class MarketplaceItem(BaseModel):
    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    item_type: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    homepage: str = ""
    price: float = 0.0  # 0.0 = free
    tags: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    min_platform_version: str = "10.0.0"
    install_count: int = 0
    rating: float = 0.0
    rating_count: int = 0
    verified: bool = False
    created_at: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateItemRequest(BaseModel):
    item_type: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    homepage: str = ""
    price: float = 0.0
    tags: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RateItemRequest(BaseModel):
    stars: float = Field(..., ge=0, le=5)


_items: dict[str, MarketplaceItem] = {}


@router.post("/items")
async def create_item(request: CreateItemRequest) -> dict[str, Any]:
    """Publish a new marketplace item."""
    item = MarketplaceItem(
        item_type=request.item_type,
        name=request.name,
        version=request.version,
        description=request.description,
        author=request.author,
        homepage=request.homepage,
        price=request.price,
        tags=request.tags,
        dependencies=request.dependencies,
        metadata=request.metadata,
    )
    _items[item.item_id] = item
    return {"item_id": item.item_id, "status": "published", "item_type": item.item_type}


@router.get("/items")
async def list_items(
    item_type: Optional[str] = None,
    tag: Optional[str] = None,
    verified_only: bool = False,
    free_only: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    """Browse marketplace items with filters."""
    items = list(_items.values())
    if item_type:
        items = [i for i in items if i.item_type == item_type]
    if tag:
        items = [i for i in items if tag in i.tags]
    if verified_only:
        items = [i for i in items if i.verified]
    if free_only:
        items = [i for i in items if i.price == 0.0]
    items.sort(key=lambda i: i.install_count, reverse=True)
    return {
        "items": [i.model_dump() for i in items[:limit]],
        "count": len(items),
    }


@router.get("/items/{item_id}")
async def get_item(item_id: str) -> dict[str, Any]:
    item = _items.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item.model_dump()


@router.post("/items/{item_id}/install")
async def install_item(item_id: str) -> dict[str, Any]:
    """Install a marketplace item (increments install count)."""
    item = _items.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    item.install_count += 1
    return {"item_id": item_id, "status": "installed", "install_count": item.install_count}


@router.post("/items/{item_id}/rate")
async def rate_item(item_id: str, request: RateItemRequest) -> dict[str, Any]:
    """Rate a marketplace item (0–5 stars)."""
    item = _items.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    total = item.rating * item.rating_count + request.stars
    item.rating_count += 1
    item.rating = total / item.rating_count
    return {"item_id": item_id, "rating": item.rating, "rating_count": item.rating_count}


@router.post("/items/{item_id}/verify")
async def verify_item(item_id: str) -> dict[str, Any]:
    """Mark a marketplace item as verified."""
    item = _items.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    item.verified = True
    return {"item_id": item_id, "verified": True}


@router.get("/types")
async def list_item_types() -> dict[str, Any]:
    """List all marketplace item types."""
    return {
        "types": [
            {"type": MarketplaceItemType.AGENT, "label": "Agents", "description": "Pre-built AI agents"},
            {"type": MarketplaceItemType.PLUGIN, "label": "Plugins", "description": "Platform extensions"},
            {"type": MarketplaceItemType.SKILL, "label": "Skills", "description": "Reusable capability packages"},
            {"type": MarketplaceItemType.TEMPLATE, "label": "Templates", "description": "Starting-point configurations"},
            {"type": MarketplaceItemType.MEMORY_PACK, "label": "Memory Packs", "description": "Pre-loaded memory items"},
            {"type": MarketplaceItemType.PROMPT_PACK, "label": "Prompt Packs", "description": "Curated prompt libraries"},
            {"type": MarketplaceItemType.WORKFLOW, "label": "Workflows", "description": "Pre-built automation workflows"},
            {"type": MarketplaceItemType.KNOWLEDGE_PACK, "label": "Knowledge Packs", "description": "Domain knowledge bundles"},
        ]
    }


@router.get("/stats")
async def marketplace_stats() -> dict[str, Any]:
    """Aggregate marketplace statistics."""
    from collections import Counter
    type_counts = Counter(i.item_type for i in _items.values())
    total_installs = sum(i.install_count for i in _items.values())
    return {
        "total_items": len(_items),
        "by_type": dict(type_counts),
        "total_installs": total_installs,
        "verified_items": sum(1 for i in _items.values() if i.verified),
    }
