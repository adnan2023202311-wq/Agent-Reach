"""
API layer: /api/v1/desktop — AI Operating System Desktop (M10.10).

Provides the manifest for the cross-platform desktop application
(Windows, macOS, Linux) and offline mode support. The desktop app wraps
the existing web frontend in Electron/Tauri and adds:
- Native OS integration (file system, notifications, tray)
- Offline mode (local execution without backend)
- Auto-update
- System tray integration

This endpoint serves the desktop manifest and offline-capable bundle
metadata so the desktop app can bootstrap itself.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/desktop", tags=["desktop"])


class DesktopManifest(BaseModel):
    """Manifest served to the desktop app on startup.

    The desktop app fetches this to know which version, features, and
    endpoints are available. It also tells the app whether offline mode
    is supported (i.e. a local backend is bundled).
    """
    platform_version: str = "10.0.0"
    desktop_version: str = "1.0.0"
    supported_os: list[str] = Field(default_factory=lambda: ["windows", "macos", "linux"])
    offline_mode: bool = True
    auto_update: bool = True
    system_tray: bool = True
    native_notifications: bool = True
    min_backend_version: str = "10.0.0"
    api_base_url: str = "/api/v1"
    web_ui_url: str = "/"
    features: list[str] = Field(default_factory=lambda: [
        "chat", "agents", "workflows", "memory", "knowledge",
        "marketplace", "observatory", "settings",
    ])


class OfflineBundle(BaseModel):
    """Describes the offline-capable bundle (shipped with the desktop app)."""
    bundle_version: str = "1.0.0"
    includes_backend: bool = True
    includes_frontend: bool = True
    bundled_providers: list[str] = Field(default_factory=lambda: ["ollama"])
    estimated_size_mb: int = 250
    last_updated: str = "2026-07-10"


@router.get("/manifest")
async def get_manifest() -> dict[str, Any]:
    """Get the desktop app manifest.

    The desktop app calls this on startup to determine which features
    are available and whether offline mode is supported.
    """
    manifest = DesktopManifest()
    return manifest.model_dump()


@router.get("/offline-bundle")
async def get_offline_bundle() -> dict[str, Any]:
    """Get metadata about the offline bundle.

    The desktop app uses this to verify the bundled backend/frontend
    are present and up to date.
    """
    bundle = OfflineBundle()
    return bundle.model_dump()


@router.get("/system-tray/config")
async def system_tray_config() -> dict[str, Any]:
    """Configuration for the system tray icon.

    Returns the menu structure and default actions the desktop app
    should show in the system tray.
    """
    return {
        "icon": "tray-icon.png",
        "tooltip": "Agent Reach",
        "menu": [
            {"label": "Open Agent Reach", "action": "open-window"},
            {"label": "Quick Chat", "action": "quick-chat"},
            {"type": "separator"},
            {"label": "New Conversation", "action": "new-conversation"},
            {"label": "Open Marketplace", "action": "open-marketplace"},
            {"type": "separator"},
            {"label": "Settings", "action": "open-settings"},
            {"label": "Quit", "action": "quit"},
        ],
        "notifications": {
            "enabled": True,
            "events": ["chat.completed", "workflow.finished", "agent.registered"],
        },
    }


@router.get("/auto-update/check")
async def check_for_updates(current_version: str = "1.0.0") -> dict[str, Any]:
    """Check if a desktop app update is available.

    The desktop app calls this periodically. Returns the latest
    available version and download URL if an update exists.
    """
    latest = "1.0.0"  # In production, read from a release manifest
    update_available = _parse_version(latest) > _parse_version(current_version)
    return {
        "current_version": current_version,
        "latest_version": latest,
        "update_available": update_available,
        "download_url": "" if not update_available else f"https://releases.agent-reach.io/desktop/{latest}",
        "release_notes": "" if not update_available else "See CHANGELOG.md",
    }


def _parse_version(v: str) -> tuple[int, int, int]:
    try:
        parts = v.strip().split(".")
        return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0, int(parts[2]) if len(parts) > 2 else 0)
    except (ValueError, IndexError):
        return (0, 0, 0)
