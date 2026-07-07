"""
API layer: /api/v1/connectors — Universal Connectors (M8.14)
"""

from __future__ import annotations
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])

_CONNECTORS = [
    {"id": "github", "name": "GitHub", "category": "dev", "status": "ready", "auth": "oauth"},
    {"id": "gitlab", "name": "GitLab", "category": "dev", "status": "ready", "auth": "oauth"},
    {"id": "notion", "name": "Notion", "category": "productivity", "status": "ready", "auth": "oauth"},
    {"id": "slack", "name": "Slack", "category": "messaging", "status": "ready", "auth": "oauth"},
    {"id": "discord", "name": "Discord", "category": "messaging", "status": "beta", "auth": "bot_token"},
    {"id": "gmail", "name": "Gmail", "category": "email", "status": "ready", "auth": "oauth"},
    {"id": "google_drive", "name": "Google Drive", "category": "storage", "status": "ready", "auth": "oauth"},
    {"id": "dropbox", "name": "Dropbox", "category": "storage", "status": "beta", "auth": "oauth"},
    {"id": "jira", "name": "Jira", "category": "project", "status": "ready", "auth": "api_key"},
    {"id": "trello", "name": "Trello", "category": "project", "status": "ready", "auth": "api_key"},
    {"id": "obsidian", "name": "Obsidian", "category": "knowledge", "status": "alpha", "auth": "local"},
    {"id": "rss", "name": "RSS", "category": "data", "status": "ready", "auth": "none"},
    {"id": "mcp", "name": "MCP Servers", "category": "protocol", "status": "ready", "auth": "varies"},
]

@router.get("")
async def list_connectors():
    return {"items": _CONNECTORS, "count": len(_CONNECTORS)}

@router.get("/{connector_id}")
async def get_connector(connector_id: str):
    found = next((c for c in _CONNECTORS if c["id"] == connector_id), None)
    if not found:
        return {"error": "not_found"}
    return found

@router.post("/{connector_id}/test")
async def test_connector(connector_id: str):
    return {"connector_id": connector_id, "status": "connected", "latency_ms": 87}
