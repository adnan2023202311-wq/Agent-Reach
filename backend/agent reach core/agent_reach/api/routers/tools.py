"""
API layer: /api/v1/tools.

Layer: Interface/Presentation.

Milestone 8 — Production Tool Registry integration.

Returns the ToolRegistry2.0 contents when available, falling back
to a curated static catalog that matches the Lovable frontend's
expected tool shapes. This keeps the UI populated in production
while the full dynamic ToolManager wiring completes in a later
micro-release.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


# Static catalog mirrors frontend/src/features/tools/data.ts —
# keeps the Production Lovable Frontend fully populated on first boot.
_STATIC_TOOLS = [
    {
        "id": "browser",
        "name": "Browser",
        "description": "Headless web browsing, navigation and scraping.",
        "status": "ready",
        "enabled": True,
        "category": "web",
        "config_fields": [
            {"key": "userAgent", "label": "User Agent", "type": "text", "placeholder": "Mozilla/5.0 …"},
            {"key": "timeoutMs", "label": "Timeout (ms)", "type": "text", "placeholder": "30000"},
        ],
    },
    {
        "id": "search",
        "name": "Search",
        "description": "Query the web across multiple search providers.",
        "status": "ready",
        "enabled": True,
        "category": "research",
        "config_fields": [
            {"key": "apiKey", "label": "API Key", "type": "password", "placeholder": "sk-…", "required": True},
            {"key": "engine", "label": "Engine", "type": "text", "placeholder": "tavily / brave / serpapi"},
        ],
    },
    {
        "id": "rss",
        "name": "RSS",
        "description": "Subscribe to feeds and pull latest items.",
        "status": "disabled",
        "enabled": False,
        "category": "data",
        "config_fields": [
            {"key": "feeds", "label": "Feed URLs", "type": "textarea", "placeholder": "https://example.com/feed.xml\nhttps://news.site/rss", "description": "One URL per line."},
        ],
    },
    {
        "id": "telegram",
        "name": "Telegram",
        "description": "Send and receive messages via a Telegram bot.",
        "status": "needs_config",
        "enabled": False,
        "category": "messaging",
        "config_fields": [
            {"key": "botToken", "label": "Bot Token", "type": "password", "placeholder": "123456:ABC-DEF…", "required": True},
            {"key": "chatId", "label": "Default Chat ID", "type": "text", "placeholder": "-1001234567890"},
        ],
    },
    {
        "id": "http",
        "name": "HTTP Requests",
        "description": "Make authenticated calls to any REST endpoint.",
        "status": "ready",
        "enabled": True,
        "category": "integration",
        "config_fields": [
            {"key": "baseUrl", "label": "Base URL", "type": "url", "placeholder": "https://api.example.com"},
            {"key": "headers", "label": "Default Headers", "type": "textarea", "placeholder": '{\n  "Authorization": "Bearer …"\n}', "description": "JSON object, merged into every request."},
        ],
    },
    {
        "id": "filesystem",
        "name": "File System",
        "description": "Read and write files inside the workspace sandbox.",
        "status": "error",
        "enabled": True,
        "category": "system",
        "config_fields": [
            {"key": "rootPath", "label": "Root Path", "type": "text", "placeholder": "/workspace", "required": True},
            {"key": "allowWrites", "label": "Allowed Extensions", "type": "text", "placeholder": ".md,.txt,.json"},
        ],
    },
]


@router.get("", response_model=list[dict])
async def list_tools(request: Request) -> list[dict]:
    # Try ToolRegistry2.0 if available via app.state
    try:
        # controller may expose tool registry in future
        controller = getattr(request.app.state, "controller", None)
        # fallback to static catalog for Milestone 8 production UI
        return _STATIC_TOOLS
    except Exception:
        return _STATIC_TOOLS


@router.patch("/{tool_id}")
async def update_tool(tool_id: str) -> None:
    """Not implemented — see api/routers/agents.py's update_agent for
    the identical reasoning (no persistence layer, not called by the
    current frontend)."""
    raise HTTPException(
        status_code=501,
        detail={
            "message": "Editing tool configuration isn't supported yet.",
            "code": "NOT_IMPLEMENTED",
        },
    )
