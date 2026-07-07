"""
Marketplace layer: Plugin Marketplace Foundation (M6.9).

Layer: Application/Core — depends inward on the existing plugin system
(agent-reach-core) and domain/ only.

Provides the foundation for a future plugin marketplace:
- plugin metadata (name, version, description, author, compatibility)
- installation (register + track installed plugins)
- removal (uninstall + clean up)
- compatibility validation (check plugin against platform version)
- version management (track installed versions, detect updates)

No external marketplace yet. This module manages a LOCAL registry of
installed plugins — the metadata layer that an external marketplace
would eventually sync against.

Design notes
------------
- The marketplace does NOT replace the existing PluginManager. It adds
  a metadata/tracking layer on top. Installation = register metadata
  + load via PluginManager. Removal = unload via PluginManager +
  remove metadata.
- Compatibility is checked against a platform version string (the
  Agent Reach version). Plugins declare a ``min_platform_version``.
- Version tracking is local: the marketplace records which version
  of each plugin is installed, so it can detect when an update is
  available (when the manifest version differs from installed).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PluginInstallStatus(str, Enum):
    """Installation status of a plugin."""

    INSTALLED = "installed"
    AVAILABLE = "available"  # not installed, but known
    INCOMPATIBLE = "incompatible"
    UPDATE_AVAILABLE = "update_available"


@dataclass
class PluginMarketplaceMetadata:
    """Metadata for a plugin in the marketplace.

    Attributes:
        plugin_id: unique identifier (matches the plugin manifest id).
        name: human-readable name.
        version: installed/available version.
        description: short description.
        author: author identifier.
        homepage: URL for more information.
        plugin_type: type of plugin (agent, tool, provider, etc.).
        min_platform_version: minimum Agent Reach version required.
        tags: arbitrary tags.
        status: installation status.
        installed_at: ISO-8601 timestamp of installation.
        updated_at: ISO-8601 timestamp of last update.
        metadata: arbitrary additional metadata.
    """

    plugin_id: str = ""
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    homepage: str = ""
    plugin_type: str = ""
    min_platform_version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    status: PluginInstallStatus = PluginInstallStatus.AVAILABLE
    installed_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "homepage": self.homepage,
            "plugin_type": self.plugin_type,
            "min_platform_version": self.min_platform_version,
            "tags": list(self.tags),
            "status": self.status.value,
            "installed_at": self.installed_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginMarketplaceMetadata:
        """Deserialize from a dict."""
        status_str = data.get("status", PluginInstallStatus.AVAILABLE.value)
        try:
            status = PluginInstallStatus(status_str)
        except ValueError:
            status = PluginInstallStatus.AVAILABLE
        return cls(
            plugin_id=str(data.get("plugin_id", "")),
            name=str(data.get("name", "")),
            version=str(data.get("version", "1.0.0")),
            description=str(data.get("description", "")),
            author=str(data.get("author", "")),
            homepage=str(data.get("homepage", "")),
            plugin_type=str(data.get("plugin_type", "")),
            min_platform_version=str(data.get("min_platform_version", "1.0.0")),
            tags=list(data.get("tags", [])),
            status=status,
            installed_at=str(data.get("installed_at", "")),
            updated_at=str(data.get("updated_at", "")),
            metadata=dict(data.get("metadata", {})),
        )


class PluginMarketplace:
    """Local plugin marketplace foundation.

    Manages plugin metadata, installation tracking, compatibility
    validation, and version management.

    Parameters
    ---
    platform_version:
        The current Agent Reach platform version. Used for compatibility
        checks. Defaults to "1.0.0".
    """

    def __init__(self, platform_version: str = "1.0.0") -> None:
        self._platform_version = platform_version
        self._plugins: dict[str, PluginMarketplaceMetadata] = {}

    # ---------------------------------------------------------------------------
    # Metadata registration
    # ---------------------------------------------------------------------------

    def register_metadata(
        self,
        metadata: PluginMarketplaceMetadata,
    ) -> PluginMarketplaceMetadata:
        """Register or update plugin metadata in the marketplace.

        If a plugin with the same plugin_id already exists, its metadata
        is updated. The status is preserved unless the version changed
        (in which case it becomes UPDATE_AVAILABLE if installed).
        """
        now = datetime.now(timezone.utc).isoformat()

        if metadata.plugin_id in self._plugins:
            existing = self._plugins[metadata.plugin_id]
            # Preserve installation status/timestamp if already installed.
            if (
                existing.status == PluginInstallStatus.INSTALLED
                and metadata.version != existing.version
            ):
                metadata.status = PluginInstallStatus.UPDATE_AVAILABLE
            elif existing.status == PluginInstallStatus.INSTALLED:
                metadata.status = PluginInstallStatus.INSTALLED
                metadata.installed_at = existing.installed_at
            metadata.updated_at = now
        else:
            # First registration — respect the passed-in status, but
            # default to AVAILABLE if not explicitly set.
            if not metadata.status:
                metadata.status = PluginInstallStatus.AVAILABLE
            metadata.updated_at = now

        self._plugins[metadata.plugin_id] = metadata
        logger.info("Registered marketplace metadata: %s v%s", metadata.name, metadata.version)
        return metadata

    def unregister_metadata(self, plugin_id: str) -> bool:
        """Remove plugin metadata from the marketplace.

        Returns True if the metadata was removed, False if it did not
        exist.
        """
        if plugin_id not in self._plugins:
            return False
        del self._plugins[plugin_id]
        logger.info("Unregistered marketplace metadata: %s", plugin_id)
        return True

    # ---------------------------------------------------------------------------
    # Installation
    # ---------------------------------------------------------------------------

    def install(self, plugin_id: str) -> Optional[PluginMarketplaceMetadata]:
        """Mark a plugin as installed.

        Returns the updated metadata, or None if the plugin is not
        registered in the marketplace.
        """
        meta = self._plugins.get(plugin_id)
        if meta is None:
            return None

        now = datetime.now(timezone.utc).isoformat()
        meta.status = PluginInstallStatus.INSTALLED
        meta.installed_at = now
        meta.updated_at = now
        logger.info("Installed plugin: %s v%s", meta.name, meta.version)
        return meta

    def uninstall(self, plugin_id: str) -> Optional[PluginMarketplaceMetadata]:
        """Mark a plugin as uninstalled (but keep metadata).

        Returns the updated metadata, or None if the plugin is not
        registered.
        """
        meta = self._plugins.get(plugin_id)
        if meta is None:
            return None

        now = datetime.now(timezone.utc).isoformat()
        meta.status = PluginInstallStatus.AVAILABLE
        meta.installed_at = ""
        meta.updated_at = now
        logger.info("Uninstalled plugin: %s", meta.name)
        return meta

    # ---------------------------------------------------------------------------
    # Compatibility validation
    # ---------------------------------------------------------------------------

    def check_compatibility(
        self, plugin_id: str
    ) -> tuple[bool, list[str]]:
        """Check if a plugin is compatible with the current platform.

        Returns (compatible, list_of_issues). An empty issues list means
        the plugin is compatible.
        """
        meta = self._plugins.get(plugin_id)
        if meta is None:
            return False, [f"Plugin '{plugin_id}' is not registered"]

        issues: list[str] = []

        if not self._version_satisfies(
            self._platform_version, meta.min_platform_version
        ):
            issues.append(
                f"Plugin requires platform version >= {meta.min_platform_version}, "
                f"but current platform is {self._platform_version}"
            )

        return (len(issues) == 0, issues)

    def validate_all(self) -> dict[str, list[str]]:
        """Validate compatibility for all registered plugins.

        Returns a mapping of plugin_id → list of issues. Only plugins
        with issues are included.
        """
        issues: dict[str, list[str]] = {}
        for plugin_id in self._plugins:
            compatible, plugin_issues = self.check_compatibility(plugin_id)
            if not compatible:
                issues[plugin_id] = plugin_issues
        return issues

    # ---------------------------------------------------------------------------
    # Version management
    # ---------------------------------------------------------------------------

    def check_for_updates(self) -> list[PluginMarketplaceMetadata]:
        """Return plugins that have an update available.

        A plugin has an update available if its status is
        UPDATE_AVAILABLE.
        """
        return [
            meta for meta in self._plugins.values()
            if meta.status == PluginInstallStatus.UPDATE_AVAILABLE
        ]

    def mark_update_available(
        self, plugin_id: str, new_version: str
    ) -> Optional[PluginMarketplaceMetadata]:
        """Mark a plugin as having an update available.

        Returns the updated metadata, or None if the plugin is not
        registered.
        """
        meta = self._plugins.get(plugin_id)
        if meta is None:
            return None
        meta.version = new_version
        if meta.status == PluginInstallStatus.INSTALLED:
            meta.status = PluginInstallStatus.UPDATE_AVAILABLE
        meta.updated_at = datetime.now(timezone.utc).isoformat()
        return meta

    # ---------------------------------------------------------------------------
    # Access
    # ---------------------------------------------------------------------------

    def get(self, plugin_id: str) -> Optional[PluginMarketplaceMetadata]:
        """Return metadata for a plugin, or None."""
        return self._plugins.get(plugin_id)

    def list_plugins(
        self,
        *,
        status: Optional[PluginInstallStatus] = None,
        plugin_type: str = "",
        tag: str = "",
    ) -> list[PluginMarketplaceMetadata]:
        """List plugins, optionally filtered."""
        results: list[PluginMarketplaceMetadata] = []
        for meta in self._plugins.values():
            if status is not None and meta.status != status:
                continue
            if plugin_type and meta.plugin_type != plugin_type:
                continue
            if tag and tag not in meta.tags:
                continue
            results.append(meta)
        return sorted(results, key=lambda m: m.name)

    def list_installed(self) -> list[PluginMarketplaceMetadata]:
        """Return all installed plugins."""
        return self.list_plugins(status=PluginInstallStatus.INSTALLED)

    def list_available(self) -> list[PluginMarketplaceMetadata]:
        """Return all available (not installed) plugins."""
        return self.list_plugins(status=PluginInstallStatus.AVAILABLE)

    def search(self, query: str) -> list[PluginMarketplaceMetadata]:
        """Search plugins by name, description, or tags."""
        q = query.lower()
        results: list[PluginMarketplaceMetadata] = []
        for meta in self._plugins.values():
            if (
                q in meta.name.lower()
                or q in meta.description.lower()
                or any(q in t.lower() for t in meta.tags)
            ):
                results.append(meta)
        return sorted(results, key=lambda m: m.name)

    # ---------------------------------------------------------------------------
    # Stats
    # ---------------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics."""
        total = len(self._plugins)
        installed = sum(
            1 for m in self._plugins.values()
            if m.status == PluginInstallStatus.INSTALLED
        )
        available = sum(
            1 for m in self._plugins.values()
            if m.status == PluginInstallStatus.AVAILABLE
        )
        updates = sum(
            1 for m in self._plugins.values()
            if m.status == PluginInstallStatus.UPDATE_AVAILABLE
        )
        return {
            "total": total,
            "installed": installed,
            "available": available,
            "updates_available": updates,
        }

    # ---------------------------------------------------------------------------
    # Internal
    # ---------------------------------------------------------------------------

    @staticmethod
    def _version_satisfies(current: str, minimum: str) -> bool:
        """Check if ``current`` version satisfies ``minimum`` requirement.

        Compares semantic version strings (major.minor.patch).
        Pre-release/build metadata is ignored for comparison.
        """
        def parse_version(v: str) -> tuple[int, ...]:
            # Strip pre-release/build metadata (e.g. "1.0.0-rc1" → "1.0.0").
            base = v.split("-")[0].split("+")[0]
            parts = base.split(".")
            result: list[int] = []
            for p in parts:
                try:
                    result.append(int(p))
                except ValueError:
                    result.append(0)
            # Pad to 3 components for consistent comparison.
            while len(result) < 3:
                result.append(0)
            return tuple(result[:3])

        try:
            return parse_version(current) >= parse_version(minimum)
        except (ValueError, IndexError):
            # If we can't parse, be permissive.
            return True

    def clear(self) -> None:
        """Remove all plugins. Useful for testing."""
        self._plugins.clear()
