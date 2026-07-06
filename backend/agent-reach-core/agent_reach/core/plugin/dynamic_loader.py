"""
Dynamic plugin loader implementation.

Discovers plugins from a filesystem directory by scanning for
plugin.json manifest files in subdirectories.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .loader_interfaces import PluginLoader
from .manifest import PluginManifest


class DynamicPluginLoader(PluginLoader):
    """
    Dynamic plugin loader that discovers plugins from the filesystem.

    Scans a root plugin directory for subdirectories containing
    a ``plugin.json`` manifest file. Each valid manifest is loaded
    and made available for discovery.
    """

    def __init__(self, plugin_dir: str) -> None:
        """Initialize with a plugin directory."""
        self._plugin_dir = plugin_dir
        self._manifests: dict[str, PluginManifest] = {}
        self._instances: dict[str, Any] = {}

    async def discover(self) -> list[str]:
        """Discover available plugins by scanning the plugin directory."""
        self._manifests.clear()

        if not os.path.exists(self._plugin_dir):
            return []

        for entry in os.listdir(self._plugin_dir):
            plugin_path = os.path.join(self._plugin_dir, entry)
            if not os.path.isdir(plugin_path):
                continue

            manifest_path = os.path.join(plugin_path, "plugin.json")
            if not os.path.exists(manifest_path):
                continue

            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                manifest = PluginManifest.from_dict(data)
                self._manifests[manifest.id] = manifest
            except Exception:
                continue

        return list(self._manifests.keys())

    async def load_manifest(self, plugin_id: str) -> PluginManifest | None:
        """Load a plugin's manifest."""
        return self._manifests.get(plugin_id)

    async def load_plugin(self, plugin_id: str) -> Any | None:
        """Load and instantiate a plugin."""
        if plugin_id in self._instances:
            return self._instances[plugin_id]

        manifest = self._manifests.get(plugin_id)
        if manifest is None:
            return None

        if not manifest.entry_point:
            return None

        try:
            module_path, class_name = manifest.entry_point.split(":")
            import importlib
            module = importlib.import_module(module_path)
            plugin_class = getattr(module, class_name)
            instance = plugin_class()
            self._instances[plugin_id] = instance
            return instance
        except Exception:
            return None

    async def unload_plugin(self, plugin_id: str) -> bool:
        """Unload a plugin."""
        if plugin_id in self._manifests:
            del self._manifests[plugin_id]
            if plugin_id in self._instances:
                del self._instances[plugin_id]
            return True
        return False
