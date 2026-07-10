"""
API layer: /api/v1/connectors/v2 — Universal Connector Framework (M10.17).

Native connectors for external services: GitHub, GitLab, Jira, Slack,
Discord, Notion, Google Workspace, Microsoft 365, AWS, Azure, GCP.

Each connector is a plugin that implements the Connector interface.
This router provides connector management, configuration, and execution.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/connectors/v2", tags=["universal-connectors"])


class Connector(BaseModel):
    connector_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    connector_type: str  # github | gitlab | jira | slack | discord | notion | gworkspace | m365 | aws | azure | gcp
    name: str
    configured: bool = False
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)  # connection-specific config (masked)
    created_at: float = Field(default_factory=time.time)
    last_sync: float = 0.0


class ConnectorAction(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    connector_id: str
    action: str  # e.g. "create_issue", "send_message", "list_repos"
    params: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    status: str = "pending"
    timestamp: float = Field(default_factory=time.time)


# Supported connector types with their capabilities
CONNECTOR_CATALOG = {
    "github": {"name": "GitHub", "capabilities": ["list_repos", "create_issue", "create_pr", "list_commits"], "auth_type": "token"},
    "gitlab": {"name": "GitLab", "capabilities": ["list_projects", "create_issue", "create_mr"], "auth_type": "token"},
    "jira": {"name": "Jira", "capabilities": ["create_issue", "list_issues", "update_issue", "add_comment"], "auth_type": "api_key"},
    "slack": {"name": "Slack", "capabilities": ["send_message", "list_channels", "create_channel"], "auth_type": "bot_token"},
    "discord": {"name": "Discord", "capabilities": ["send_message", "list_servers"], "auth_type": "bot_token"},
    "notion": {"name": "Notion", "capabilities": ["create_page", "query_database", "list_databases"], "auth_type": "token"},
    "gworkspace": {"name": "Google Workspace", "capabilities": ["send_email", "create_event", "list_files"], "auth_type": "oauth"},
    "m365": {"name": "Microsoft 365", "capabilities": ["send_email", "create_event", "list_files"], "auth_type": "oauth"},
    "aws": {"name": "AWS", "capabilities": ["list_instances", "start_instance", "stop_instance", "list_buckets"], "auth_type": "access_key"},
    "azure": {"name": "Azure", "capabilities": ["list_resources", "start_vm", "stop_vm"], "auth_type": "service_principal"},
    "gcp": {"name": "Google Cloud", "capabilities": ["list_instances", "start_instance", "stop_instance"], "auth_type": "service_account"},
}

_connectors: dict[str, Connector] = {}
_actions: list[ConnectorAction] = []


@router.get("/catalog")
async def connector_catalog() -> dict[str, Any]:
    """List all supported connector types and their capabilities."""
    return {"connectors": CONNECTOR_CATALOG, "count": len(CONNECTOR_CATALOG)}


class ConfigureConnectorRequest(BaseModel):
    connector_type: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)


@router.post("")
async def configure_connector(request: ConfigureConnectorRequest) -> dict[str, Any]:
    """Configure a new connector instance."""
    if request.connector_type not in CONNECTOR_CATALOG:
        raise HTTPException(status_code=400, detail=f"Unknown connector type: {request.connector_type}")
    connector = Connector(
        connector_type=request.connector_type,
        name=request.name,
        config=request.config,
        configured=bool(request.config),
    )
    _connectors[connector.connector_id] = connector
    return {"connector_id": connector.connector_id, "name": connector.name, "configured": connector.configured}


@router.get("")
async def list_connectors(connector_type: Optional[str] = None) -> dict[str, Any]:
    """List configured connectors."""
    connectors = list(_connectors.values())
    if connector_type:
        connectors = [c for c in connectors if c.connector_type == connector_type]
    return {"connectors": [c.model_dump() for c in connectors], "count": len(connectors)}


@router.get("/{connector_id}")
async def get_connector(connector_id: str) -> dict[str, Any]:
    """Get one connector's configuration."""
    connector = _connectors.get(connector_id)
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    # Mask sensitive config values
    masked = {k: ("***" if any(s in k.lower() for s in ("key", "token", "secret", "password")) else v)
              for k, v in connector.config.items()}
    return {**connector.model_dump(), "config": masked}


@router.delete("/{connector_id}")
async def delete_connector(connector_id: str) -> dict[str, Any]:
    """Delete a connector."""
    if _connectors.pop(connector_id, None) is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    return {"status": "deleted"}


class ExecuteActionRequest(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/{connector_id}/execute")
async def execute_action(connector_id: str, request: ExecuteActionRequest) -> dict[str, Any]:
    """Execute an action through a connector."""
    connector = _connectors.get(connector_id)
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    if not connector.configured:
        raise HTTPException(status_code=400, detail="Connector is not configured")
    catalog = CONNECTOR_CATALOG.get(connector.connector_type, {})
    if request.action not in catalog.get("capabilities", []):
        raise HTTPException(status_code=400, detail=f"Action '{request.action}' not supported by {connector.connector_type}")
    action = ConnectorAction(
        connector_id=connector_id, action=request.action, params=request.params,
        result={"status": "simulated", "message": f"In production, this would call {connector.name}'s API"},
        status="completed",
    )
    _actions.append(action)
    connector.last_sync = time.time()
    return {"action_id": action.action_id, "result": action.result, "status": "completed"}


@router.get("/actions/recent")
async def recent_actions(limit: int = 20) -> dict[str, Any]:
    """List recent connector actions."""
    return {"actions": [a.model_dump() for a in _actions[-limit:]], "count": len(_actions)}
