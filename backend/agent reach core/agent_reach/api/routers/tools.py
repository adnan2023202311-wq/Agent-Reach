"""
API layer: /api/v1/tools.

Layer: Interface/Presentation.

M9.6 — Live Tool Runtime. The M8 static catalog is gone: this router
now reports the real ToolRegistry contents (metadata, versions,
categories, enabled state) and executes real tools through the
ToolRuntime, which records execution history, failures, retries, and
metrics. Status values are derived from actual registry state, not
hardcoded strings.

Config field metadata (which inputs a tool needs) stays here in the
presentation layer — it describes UI forms, not runtime behavior.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


# UI form descriptions per tool — presentation metadata only.
_CONFIG_FIELDS: dict[str, list[dict[str, Any]]] = {
    "http_request": [
        {"key": "url", "label": "URL", "type": "url", "required": True},
        {"key": "method", "label": "Method", "type": "text", "placeholder": "GET"},
        {"key": "headers", "label": "Headers", "type": "textarea", "placeholder": '{"Authorization": "Bearer …"}'},
    ],
    "rss_fetch": [
        {"key": "url", "label": "Feed URL", "type": "url", "required": True},
        {"key": "max_items", "label": "Max Items", "type": "text", "placeholder": "20"},
    ],
    "browser_fetch": [
        {"key": "url", "label": "Page URL", "type": "url", "required": True},
    ],
    "fs_read": [
        {"key": "path", "label": "File Path", "type": "text", "required": True},
    ],
    "fs_write": [
        {"key": "path", "label": "File Path", "type": "text", "required": True},
        {"key": "content", "label": "Content", "type": "textarea", "required": True},
    ],
    "fs_list": [
        {"key": "path", "label": "Directory", "type": "text", "placeholder": "."},
    ],
    "telegram_send": [
        {"key": "chat_id", "label": "Chat ID", "type": "text", "required": True},
        {"key": "text", "label": "Message", "type": "textarea", "required": True},
    ],
}


class ToolExecuteRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    agent_type: str = "api"
    timeout_seconds: Optional[float] = None


def _get_tool_runtime(request: Request):
    runtime = getattr(request.app.state, "tool_runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Tool runtime not available")
    return runtime


def _summarize(meta: Any) -> dict[str, Any]:
    return {
        "id": meta.name,
        "name": meta.name.replace("_", " ").title(),
        "description": meta.description,
        "status": "ready" if meta.enabled else "disabled",
        "enabled": meta.enabled,
        "category": meta.category or "uncategorized",
        "version": meta.version,
        "tags": list(meta.tags),
        "call_count": meta.call_count,
        "config_fields": _CONFIG_FIELDS.get(meta.name, []),
    }


@router.get("", response_model=list[dict])
async def list_tools(request: Request) -> list[dict]:
    """List every registered tool with live registry metadata."""
    runtime = _get_tool_runtime(request)
    return [_summarize(m) for m in runtime.registry.list_tools()]


@router.get("/metrics")
async def tool_metrics(request: Request) -> dict[str, Any]:
    """Aggregate + per-tool execution metrics (M9.6)."""
    runtime = _get_tool_runtime(request)
    return {
        "overall": runtime.get_metrics(),
        "per_tool": runtime.get_per_tool_metrics(),
        "registry": runtime.registry.get_stats(),
    }


@router.get("/history")
async def tool_history(
    request: Request,
    tool_id: str = "",
    limit: int = 50,
    failures_only: bool = False,
) -> dict[str, Any]:
    """Recent tool executions, newest first (M9.6)."""
    runtime = _get_tool_runtime(request)
    records = runtime.get_history(
        tool_name=tool_id, limit=limit, failures_only=failures_only
    )
    return {"executions": [r.to_dict() for r in records], "count": len(records)}


@router.get("/{tool_id}")
async def get_tool(tool_id: str, request: Request) -> dict[str, Any]:
    """One tool's metadata plus its execution metrics and history."""
    runtime = _get_tool_runtime(request)
    meta = runtime.registry.get_metadata(tool_id)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Tool '{tool_id}' is not registered.", "code": "TOOL_NOT_FOUND"},
        )
    return {
        **_summarize(meta),
        "metrics": runtime.get_metrics(tool_id),
        "recent_executions": [r.to_dict() for r in runtime.get_history(tool_name=tool_id, limit=10)],
    }


@router.post("/{tool_id}/execute")
async def execute_tool(
    tool_id: str, body: ToolExecuteRequest, request: Request
) -> dict[str, Any]:
    """Execute a real tool through the ToolRuntime (M9.6).

    Failures are returned as structured records (success=False), never
    swallowed — the execution is always recorded in history.
    """
    runtime = _get_tool_runtime(request)
    if runtime.registry.get_metadata(tool_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Tool '{tool_id}' is not registered.", "code": "TOOL_NOT_FOUND"},
        )
    record = await runtime.execute(
        tool_id,
        agent_type=body.agent_type,
        parameters=body.parameters,
        timeout_seconds=body.timeout_seconds,
    )
    return record.to_dict()


@router.patch("/{tool_id}")
async def update_tool(tool_id: str, body: dict, request: Request) -> dict[str, Any]:
    """Enable or disable a tool at runtime (M9.6).

    Only `enabled` is mutable — credentials still come from the
    environment (see api/routers/providers.py for the reasoning).
    """
    runtime = _get_tool_runtime(request)
    meta = runtime.registry.get_metadata(tool_id)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Tool '{tool_id}' is not registered.", "code": "TOOL_NOT_FOUND"},
        )
    if "enabled" not in body:
        raise HTTPException(
            status_code=422,
            detail={"message": "Only the 'enabled' field can be updated.", "code": "INVALID_UPDATE"},
        )
    if bool(body["enabled"]):
        runtime.registry.enable(tool_id)
    else:
        runtime.registry.disable(tool_id)
    return _summarize(runtime.registry.get_metadata(tool_id))
