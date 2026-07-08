"""
API layer: /api/v1/connectors — Universal Connectors (M9.1).

Layer: Interface/Presentation.

M9.1 replaces the M8 mock, which advertised 13 integrations (GitHub,
Notion, Slack, ...) that had NO implementation behind them and a
/test endpoint that returned "connected" with an invented 87ms for
any id. This version derives the connector list from what actually
exists in the runtime:

- Tool-backed connectors: production tools in the LIVE ToolRegistry
  (http, rss, browser, filesystem, telegram) — status mirrors the
  tool's real enabled state.
- MCP: the real MCPRuntime with its registered tool count.

/test performs a REAL connectivity check where one is possible
(executing the underlying tool through the ToolRuntime, recorded in
its history) and honestly refuses where it isn't.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])


# Connector id → (underlying tool, category, test parameters builder).
# Test parameters use safe, side-effect-free operations.
_TOOL_CONNECTORS: dict[str, dict[str, Any]] = {
    "http": {
        "name": "HTTP",
        "tool": "http_request",
        "category": "integration",
        "auth": "none",
        "test_parameters": None,  # needs a target URL from the caller
    },
    "rss": {
        "name": "RSS",
        "tool": "rss_fetch",
        "category": "data",
        "auth": "none",
        "test_parameters": None,  # needs a feed URL from the caller
    },
    "browser": {
        "name": "Browser",
        "tool": "browser_fetch",
        "category": "web",
        "auth": "none",
        "test_parameters": None,
    },
    "filesystem": {
        "name": "File System",
        "tool": "fs_list",
        "category": "system",
        "auth": "local",
        "test_parameters": {"path": "."},  # sandbox root listing is safe
    },
    "telegram": {
        "name": "Telegram",
        "tool": "telegram_send",
        "category": "messaging",
        "auth": "bot_token",
        "test_parameters": None,  # a real test would send a message
    },
}


class ConnectorTestRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)


def _tool_runtime(request: Request):
    runtime = getattr(request.app.state, "tool_runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Tool runtime not available")
    return runtime


def _summarize_tool_connector(connector_id: str, spec: dict[str, Any], runtime) -> dict[str, Any]:
    meta = runtime.registry.get_metadata(spec["tool"])
    if meta is None:
        status = "unavailable"
        enabled = False
    else:
        enabled = meta.enabled
        status = "ready" if meta.enabled else "disabled"
    return {
        "id": connector_id,
        "name": spec["name"],
        "category": spec["category"],
        "auth": spec["auth"],
        "status": status,
        "enabled": enabled,
        "backing_tool": spec["tool"],
        "testable_without_parameters": spec["test_parameters"] is not None,
    }


def _summarize_mcp(request: Request) -> dict[str, Any]:
    """The MCP connector reflects the real MCPRuntime state."""
    tool_count = 0
    available = False
    try:
        from mcp.runtime import MCPRuntime

        mcp_runtime = getattr(request.app.state, "mcp_runtime", None)
        if mcp_runtime is None:
            mcp_runtime = MCPRuntime()
            request.app.state.mcp_runtime = mcp_runtime
        tool_count = len(mcp_runtime.list_tools())
        available = True
    except Exception:
        pass
    return {
        "id": "mcp",
        "name": "MCP Servers",
        "category": "protocol",
        "auth": "varies",
        "status": "ready" if available else "unavailable",
        "enabled": available,
        "registered_tools": tool_count,
        "testable_without_parameters": False,
    }


@router.get("")
async def list_connectors(request: Request) -> dict[str, Any]:
    """Connectors derived from the real runtime — no fictional catalog."""
    runtime = _tool_runtime(request)
    items = [
        _summarize_tool_connector(cid, spec, runtime)
        for cid, spec in _TOOL_CONNECTORS.items()
    ]
    items.append(_summarize_mcp(request))
    return {"items": items, "count": len(items)}


@router.get("/{connector_id}")
async def get_connector(connector_id: str, request: Request) -> dict[str, Any]:
    runtime = _tool_runtime(request)
    if connector_id == "mcp":
        return _summarize_mcp(request)
    spec = _TOOL_CONNECTORS.get(connector_id)
    if spec is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"Connector '{connector_id}' not found.",
                "code": "CONNECTOR_NOT_FOUND",
            },
        )
    summary = _summarize_tool_connector(connector_id, spec, runtime)
    # Include the backing tool's real execution metrics.
    summary["metrics"] = runtime.get_metrics(spec["tool"])
    return summary


@router.post("/{connector_id}/test")
async def test_connector(
    connector_id: str, request: Request, body: Optional[ConnectorTestRequest] = None
) -> dict[str, Any]:
    """REAL connectivity test through the backing tool.

    The M8 mock returned "connected" + 87ms for any id. This executes
    the underlying tool via the ToolRuntime (recorded in its history)
    and returns the real outcome. Connectors whose test needs caller
    parameters (a URL, a chat id) reject parameterless tests honestly
    instead of faking success.
    """
    if connector_id == "mcp":
        summary = _summarize_mcp(request)
        return {
            "connector_id": "mcp",
            "success": summary["enabled"],
            "detail": f"MCP runtime reachable; {summary['registered_tools']} tools registered.",
        }

    spec = _TOOL_CONNECTORS.get(connector_id)
    if spec is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"Connector '{connector_id}' not found.",
                "code": "CONNECTOR_NOT_FOUND",
            },
        )

    parameters = dict(body.parameters) if body else {}
    if not parameters:
        if spec["test_parameters"] is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": (
                        f"Connector '{connector_id}' needs test parameters "
                        f"(e.g. a target URL) — a parameterless test cannot "
                        f"prove connectivity."
                    ),
                    "code": "TEST_PARAMETERS_REQUIRED",
                },
            )
        parameters = dict(spec["test_parameters"])

    runtime = _tool_runtime(request)
    record = await runtime.execute(
        spec["tool"], agent_type="connector-test", parameters=parameters
    )
    return {
        "connector_id": connector_id,
        "success": record.success,
        "latency_ms": record.duration_ms,  # measured, not invented
        "error": record.error,
        "execution_id": record.execution_id,
    }
