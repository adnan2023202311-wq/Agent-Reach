"""
API layer: /api/v1/marketplace — Plugin Marketplace (M9.22 / M9.1).

Layer: Interface/Presentation.

M9 replaces the M8 mock (hardcoded plugin list with invented download
counts and ratings; install/uninstall that always "succeeded") with
the REAL PluginMarketplace engine (marketplace/__init__.py, built in
M8 but never wired to the API):

- The catalog is seeded from the platform's actual built-in
  capabilities: every production tool registered in the ToolRuntime
  becomes a marketplace entry (source of truth: the live registry).
- install/uninstall mutate real marketplace state and 404 for unknown
  plugins instead of returning fake success.
- Compatibility checks, updates, search, and stats are the engine's
  real implementations.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from marketplace import PluginInstallStatus, PluginMarketplace, PluginMarketplaceMetadata

router = APIRouter(prefix="/api/v1/marketplace", tags=["marketplace"])


class PluginInstallRequest(BaseModel):
    plugin_id: str
    version: str = "latest"


def _marketplace(request: Request) -> PluginMarketplace:
    marketplace = getattr(request.app.state, "plugin_marketplace", None)
    if marketplace is None:
        raise HTTPException(status_code=503, detail="Marketplace not available")
    return marketplace


def seed_marketplace_from_tools(
    marketplace: PluginMarketplace, tool_runtime: Any
) -> None:
    """Seed the marketplace catalog from the LIVE tool registry.

    Every registered production tool becomes a marketplace entry —
    real names, versions, and categories from ToolMetadata. Installed
    status mirrors the tool's enabled flag.
    """
    for meta in tool_runtime.registry.list_tools():
        marketplace.register_metadata(
            PluginMarketplaceMetadata(
                plugin_id=meta.name,
                name=meta.name.replace("_", " ").title(),
                version=meta.version,
                description=meta.description,
                author="AgentReach",
                plugin_type="tool",
                tags=list(meta.tags),
                status=(
                    PluginInstallStatus.INSTALLED
                    if meta.enabled
                    else PluginInstallStatus.AVAILABLE
                ),
            )
        )


@router.get("/plugins")
async def list_marketplace_plugins(
    request: Request,
    status: Optional[str] = None,
    query: str = "",
) -> dict[str, Any]:
    """List catalog plugins from the real marketplace engine."""
    marketplace = _marketplace(request)
    if query:
        plugins = marketplace.search(query)
    elif status:
        try:
            wanted = PluginInstallStatus(status)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"Unknown status '{status}'. "
                    f"Valid: {[s.value for s in PluginInstallStatus]}",
                    "code": "INVALID_STATUS",
                },
            ) from exc
        plugins = marketplace.list_plugins(status=wanted)
    else:
        plugins = marketplace.list_plugins()
    return {"items": [p.to_dict() for p in plugins], "count": len(plugins)}


@router.get("/plugins/stats")
async def marketplace_stats(request: Request) -> dict[str, Any]:
    """Real marketplace statistics."""
    return _marketplace(request).get_stats()


@router.get("/plugins/updates")
async def marketplace_updates(request: Request) -> dict[str, Any]:
    """Plugins with available updates."""
    updates = _marketplace(request).check_for_updates()
    return {"items": [p.to_dict() for p in updates], "count": len(updates)}


@router.get("/plugins/{plugin_id}")
async def get_marketplace_plugin(plugin_id: str, request: Request) -> dict[str, Any]:
    """One plugin's metadata + compatibility report."""
    marketplace = _marketplace(request)
    meta = marketplace.get(plugin_id)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Plugin '{plugin_id}' not found.", "code": "PLUGIN_NOT_FOUND"},
        )
    compatible, problems = marketplace.check_compatibility(plugin_id)
    return {**meta.to_dict(), "compatible": compatible, "compatibility_problems": problems}


@router.post("/plugins/install")
async def install_plugin(req: PluginInstallRequest, request: Request) -> dict[str, Any]:
    """Install a plugin — 404 for unknown ids, no fake success."""
    marketplace = _marketplace(request)
    compatible, problems = marketplace.check_compatibility(req.plugin_id)
    if marketplace.get(req.plugin_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Plugin '{req.plugin_id}' not found.", "code": "PLUGIN_NOT_FOUND"},
        )
    if not compatible:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Plugin '{req.plugin_id}' is incompatible: {problems}",
                "code": "INCOMPATIBLE_PLUGIN",
            },
        )
    meta = marketplace.install(req.plugin_id)
    return meta.to_dict()


@router.delete("/plugins/{plugin_id}")
async def uninstall_plugin(plugin_id: str, request: Request) -> dict[str, Any]:
    """Uninstall a plugin — 404 for unknown ids."""
    marketplace = _marketplace(request)
    meta = marketplace.uninstall(plugin_id)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Plugin '{plugin_id}' not found.", "code": "PLUGIN_NOT_FOUND"},
        )
    return meta.to_dict()
