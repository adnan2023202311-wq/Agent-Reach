"""
API layer: /api/v1/dev-platform — Public Developer Platform (M10.5).

Provides API key management, usage tracking, and developer
documentation endpoints. This is the surface third-party developers
use to integrate with Agent Reach.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/dev-platform", tags=["developer-platform"])


# ── API Key store (in-memory; swap for DB in production) ────────────────

class APIKey:
    """One developer API key."""

    def __init__(self, key_id: str, key_secret: str, name: str, owner: str = "") -> None:
        self.key_id = key_id
        # Store only the hash of the secret — never the plaintext.
        self.key_hash = hashlib.sha256(key_secret.encode()).hexdigest()
        self.key_prefix = key_secret[:8]  # for display: "ar-xxxx..."
        self.name = name
        self.owner = owner
        self.created_at = time.time()
        self.last_used = 0.0
        self.request_count = 0
        self.enabled = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "key_prefix": self.key_prefix,
            "name": self.name,
            "owner": self.owner,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "request_count": self.request_count,
            "enabled": self.enabled,
        }


class _APIKeyStore:
    """In-memory API key store. Singleton via get_api_key_store()."""

    def __init__(self) -> None:
        self._keys: dict[str, APIKey] = {}  # key_id → APIKey
        self._hash_to_id: dict[str, str] = {}  # key_hash → key_id

    def create(self, name: str, owner: str = "") -> tuple[APIKey, str]:
        """Create a new API key. Returns (APIKey, plaintext_secret).

        The plaintext secret is ONLY returned at creation time — it's
        not stored. The caller must save it; subsequent lookups are by
        hash.
        """
        key_id = f"key_{secrets.token_hex(8)}"
        key_secret = f"ar_{secrets.token_hex(24)}"
        api_key = APIKey(key_id, key_secret, name, owner)
        self._keys[key_id] = api_key
        self._hash_to_id[api_key.key_hash] = key_id
        return api_key, key_secret

    def verify(self, bearer_token: str) -> Optional[APIKey]:
        """Verify a bearer token. Returns the APIKey if valid, None otherwise."""
        if not bearer_token:
            return None
        token = bearer_token.removeprefix("Bearer ").strip()
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        key_id = self._hash_to_id.get(key_hash)
        if key_id is None:
            return None
        api_key = self._keys.get(key_id)
        if api_key is None or not api_key.enabled:
            return None
        api_key.last_used = time.time()
        api_key.request_count += 1
        return api_key

    def list(self, owner: Optional[str] = None) -> list[APIKey]:
        keys = list(self._keys.values())
        if owner:
            keys = [k for k in keys if k.owner == owner]
        return keys

    def revoke(self, key_id: str) -> bool:
        api_key = self._keys.pop(key_id, None)
        if api_key is None:
            return False
        self._hash_to_id.pop(api_key.key_hash, None)
        return True

    def stats(self) -> dict[str, Any]:
        return {
            "total_keys": len(self._keys),
            "active_keys": sum(1 for k in self._keys.values() if k.enabled),
            "total_requests": sum(k.request_count for k in self._keys.values()),
        }


_store: Optional[_APIKeyStore] = None


def get_api_key_store() -> _APIKeyStore:
    global _store
    if _store is None:
        _store = _APIKeyStore()
    return _store


# ── Schemas ─────────────────────────────────────────────────────────────

class CreateAPIKeyRequest(BaseModel):
    name: str = Field(..., description="Human-readable name for the key")
    owner: str = ""


class CreateAPIKeyResponse(BaseModel):
    key_id: str
    key_secret: str  # only returned once
    name: str
    message: str = "Save this secret — it won't be shown again."


# ── Endpoints ───────────────────────────────────────────────────────────

@router.post("/api-keys")
async def create_api_key(request: CreateAPIKeyRequest) -> dict[str, Any]:
    """Create a new API key. The secret is returned ONCE."""
    store = get_api_key_store()
    api_key, secret = store.create(request.name, request.owner)
    return {
        "key_id": api_key.key_id,
        "key_secret": secret,
        "name": api_key.name,
        "message": "Save this secret — it won't be shown again.",
    }


@router.get("/api-keys")
async def list_api_keys(owner: Optional[str] = None) -> dict[str, Any]:
    """List API keys (without secrets)."""
    store = get_api_key_store()
    keys = store.list(owner=owner)
    return {"keys": [k.to_dict() for k in keys], "count": len(keys)}


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: str) -> dict[str, Any]:
    """Revoke an API key."""
    store = get_api_key_store()
    if not store.revoke(key_id):
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "revoked", "key_id": key_id}


@router.get("/api-keys/stats")
async def api_key_stats() -> dict[str, Any]:
    """Aggregate API key usage stats."""
    return get_api_key_store().stats()


@router.get("/docs")
async def developer_docs() -> dict[str, Any]:
    """Developer documentation — API surface overview.

    Returns a structured description of every API endpoint group,
    so developers can discover the platform's capabilities without
    reading the source.
    """
    return {
        "platform": "Agent Reach",
        "version": "10.0.0",
        "base_url": "/api/v1",
        "authentication": {
            "type": "bearer",
            "header": "Authorization: Bearer ar_...",
            "endpoint": "/api/v1/dev-platform/api-keys",
        },
        "endpoint_groups": [
            {"path": "/chat", "description": "Send a chat message through the intelligent pipeline"},
            {"path": "/conversations", "description": "Multi-turn conversation sessions"},
            {"path": "/agents", "description": "Agent management and listing"},
            {"path": "/agents/global", "description": "Global agent registry (M10.3)"},
            {"path": "/providers", "description": "Provider configuration and status"},
            {"path": "/tools", "description": "Tool registry and execution"},
            {"path": "/workflows", "description": "Workflow creation and execution"},
            {"path": "/memory", "description": "Memory store operations"},
            {"path": "/knowledge", "description": "Knowledge graph operations"},
            {"path": "/marketplace", "description": "Plugin marketplace"},
            {"path": "/observatory", "description": "Runtime observability"},
            {"path": "/distributed", "description": "Distributed agent cloud + swarms (M10.1/M10.2)"},
            {"path": "/sdk", "description": "Plugin SDK registry (M10.4)"},
            {"path": "/dev-platform", "description": "Developer platform (this endpoint group, M10.5)"},
            {"path": "/workflows/v2", "description": "Visual Workflow Builder V2 (M10.6)"},
            {"path": "/enterprise", "description": "Enterprise: orgs, teams, RBAC (M10.7)"},
            {"path": "/apps", "description": "AI Application Builder (M10.8)"},
            {"path": "/marketplace/v2", "description": "Marketplace V2 (M10.9)"},
        ],
        "sdks": [
            {"language": "python", "package": "agent-reach", "status": "available"},
            {"language": "javascript", "package": "@agent-reach/sdk", "status": "planned"},
        ],
        "webhooks": {
            "status": "planned",
            "events": ["chat.completed", "workflow.finished", "agent.registered"],
        },
    }


# ── Auth dependency (for other routers to use) ──────────────────────────

async def require_api_key(authorization: Optional[str] = Header(None)) -> APIKey:
    """FastAPI dependency that verifies an API key.

    Usage in a router:
        from api.routers.dev_platform import require_api_key
        @router.get("/protected", dependencies=[Depends(require_api_key)])
        async def protected(): ...
    """
    store = get_api_key_store()
    api_key = store.verify(authorization or "")
    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key
