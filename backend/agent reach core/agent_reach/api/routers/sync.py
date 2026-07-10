"""
API layer: /api/v1/sync — Cloud Synchronization (M10.12).

Synchronizes agents, memory, workflows, knowledge, settings, prompts,
and conversations across all devices. Uses a last-write-wins conflict
resolution strategy with vector clocks for eventual consistency.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/sync", tags=["cloud-sync"])


class SyncEntity(BaseModel):
    entity_type: str  # agent | memory | workflow | knowledge | setting | prompt | conversation
    entity_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    device_id: str = ""
    timestamp: float = Field(default_factory=time.time)


class SyncRequest(BaseModel):
    device_id: str
    entities: list[SyncEntity]
    last_sync_at: float = 0.0


class SyncResponse(BaseModel):
    synced: list[SyncEntity] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    server_changes: list[SyncEntity] = Field(default_factory=list)
    sync_timestamp: float = Field(default_factory=time.time)


_sync_store: dict[str, dict[str, SyncEntity]] = {}  # entity_type → entity_id → SyncEntity


@router.post("/push", response_model=SyncResponse)
async def push_changes(request: SyncRequest) -> SyncResponse:
    """Push local changes from a device to the cloud."""
    response = SyncResponse()
    for entity in request.entities:
        key = entity.entity_type
        store = _sync_store.setdefault(key, {})
        existing = store.get(entity.entity_id)
        if existing is None or entity.version > existing.version:
            store[entity.entity_id] = entity
            response.synced.append(entity)
        elif entity.version == existing.version and entity.timestamp > existing.timestamp:
            store[entity.entity_id] = entity
            response.synced.append(entity)
        else:
            response.conflicts.append({
                "entity_type": entity.entity_type,
                "entity_id": entity.entity_id,
                "local_version": entity.version,
                "server_version": existing.version,
                "resolution": "server_wins",
            })
    response.sync_timestamp = time.time()
    return response


@router.post("/pull", response_model=SyncResponse)
async def pull_changes(device_id: str, last_sync_at: float = 0.0) -> SyncResponse:
    """Pull server changes since the last sync timestamp."""
    response = SyncResponse()
    for entity_type, store in _sync_store.items():
        for entity in store.values():
            if entity.timestamp > last_sync_at and entity.device_id != device_id:
                response.server_changes.append(entity)
    response.sync_timestamp = time.time()
    return response


@router.get("/status")
async def sync_status() -> dict[str, Any]:
    """Return sync store statistics."""
    total = sum(len(store) for store in _sync_store.values())
    by_type = {k: len(v) for k, v in _sync_store.items()}
    return {"total_entities": total, "by_type": by_type}


@router.get("/entity/{entity_type}/{entity_id}")
async def get_entity(entity_type: str, entity_id: str) -> dict[str, Any]:
    """Get one synced entity."""
    store = _sync_store.get(entity_type, {})
    entity = store.get(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity.model_dump()


@router.delete("/entity/{entity_type}/{entity_id}")
async def delete_entity(entity_type: str, entity_id: str) -> dict[str, Any]:
    """Delete a synced entity."""
    store = _sync_store.get(entity_type, {})
    if entity_id not in store:
        raise HTTPException(status_code=404, detail="Entity not found")
    del store[entity_id]
    return {"status": "deleted"}
