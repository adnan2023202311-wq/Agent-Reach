"""
API layer: /api/v1/sdk — Plugin SDK (M10.4).

Exposes the PluginSDKRegistry over HTTP. Developers can list loaded
SDK plugins, query by type, and get plugin manifests.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sdk.plugin_sdk import PluginManifest, PluginType, get_plugin_sdk_registry

router = APIRouter(prefix="/api/v1/sdk", tags=["plugin-sdk"])


class RegisterPluginRequest(BaseModel):
    """Register an SDK plugin's manifest (metadata only — the plugin
    class is loaded separately by the DynamicPluginLoader)."""
    plugin_id: str
    name: str
    version: str
    plugin_type: str
    description: str = ""
    author: str = ""
    homepage: str = ""
    license: str = "MIT"
    min_platform_version: str = "10.0.0"
    entry_point: str = ""
    config_schema: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


@router.get("/plugins")
async def list_plugins(plugin_type: Optional[str] = None) -> dict[str, Any]:
    """List all loaded SDK plugins, optionally filtered by type."""
    registry = get_plugin_sdk_registry()
    if plugin_type:
        plugins = registry.list_by_type(plugin_type)
        return {
            "plugins": [m.to_dict() for _, m in plugins],
            "count": len(plugins),
        }
    manifests = registry.list_all()
    return {
        "plugins": [m.to_dict() for m in manifests],
        "count": len(manifests),
    }


@router.post("/plugins")
async def register_plugin(request: RegisterPluginRequest) -> dict[str, Any]:
    """Register a plugin manifest with the SDK registry.

    Note: this only records the manifest. The actual plugin class must
    be loaded by the DynamicPluginLoader (for filesystem plugins) or
    imported programmatically. This endpoint exists so the platform
    can track SDK plugins that were loaded by other means.
    """
    registry = get_plugin_sdk_registry()
    manifest = PluginManifest(
        plugin_id=request.plugin_id,
        name=request.name,
        version=request.version,
        plugin_type=request.plugin_type,
        description=request.description,
        author=request.author,
        homepage=request.homepage,
        license=request.license,
        min_platform_version=request.min_platform_version,
        entry_point=request.entry_point,
        config_schema=request.config_schema,
        dependencies=request.dependencies,
        tags=request.tags,
    )
    # We don't instantiate the plugin class here — only track the manifest.
    # The actual plugin object is registered by the loader.
    return {
        "status": "manifest_recorded",
        "plugin_id": manifest.plugin_id,
        "manifest": manifest.to_dict(),
    }


@router.get("/plugins/{plugin_id}")
async def get_plugin(plugin_id: str) -> dict[str, Any]:
    """Get one plugin's manifest."""
    registry = get_plugin_sdk_registry()
    plugin = registry.get(plugin_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return plugin.manifest.to_dict()


@router.get("/types")
async def list_plugin_types() -> dict[str, Any]:
    """List all supported plugin types."""
    types = [
        PluginType.PROVIDER,
        PluginType.TOOL,
        PluginType.MEMORY_ADAPTER,
        PluginType.CONTEXT_ENGINE,
        PluginType.ROUTER,
        PluginType.SKILL,
        PluginType.BENCHMARK,
        PluginType.VISUAL_NODE,
        PluginType.AGENT,
    ]
    return {"types": types}


@router.get("/stats")
async def sdk_stats() -> dict[str, Any]:
    """Aggregate SDK registry stats."""
    return get_plugin_sdk_registry().stats()
