"""
Static plugin loader implementation.

Loads plugins from a predefined list (no dynamic discovery).
Useful for development and testing.
"""

from __future__ import annotations

from typing import Any

from .loader_interfaces import PluginLoader
from .manifest import PluginManifest


class StaticPluginLoader(PluginLoader):
    """
    Static plugin loader that uses a predefined plugin registry.
    
    Plugins must be registered manually before they can be discovered/loaded.
    This is useful for:
    - Development and testing
    - Cases where dynamic discovery is not needed
    - Controlling exactly which plugins are available
    """
    
    def __init__(self) -> None:
        """Initialize with an empty plugin registry."""
        self._plugins: dict[str, PluginManifest] = {}
        self._instances: dict[str, Any] = {}
    
    async def discover(self) -> list[str]:
        """
        Return all registered plugin IDs.
        
        Returns:
            List of plugin IDs
        """
        return list(self._plugins.keys())
    
    async def load_manifest(self, plugin_id: str) -> PluginManifest | None:
        """
        Load a plugin's manifest.
        
        Args:
            plugin_id: The ID of the plugin
            
        Returns:
            The plugin manifest, or None if not found
        """
        return self._plugins.get(plugin_id)
    
    async def load_plugin(self, plugin_id: str) -> Any | None:
        """
        Load and instantiate a plugin.
        
        Args:
            plugin_id: The ID of the plugin
            
        Returns:
            The instantiated plugin object, or None if not found
        """
        # Check if already instantiated
        if plugin_id in self._instances:
            return self._instances[plugin_id]
        
        # Get manifest
        manifest = self._plugins.get(plugin_id)
        if manifest is None:
            return None
        
        # Instantiate plugin from entry_point
        # entry_point format: "module.path:ClassName"
        try:
            module_path, class_name = manifest.entry_point.split(":")
            import importlib
            module = importlib.import_module(module_path)
            plugin_class = getattr(module, class_name)
            instance = plugin_class()
            self._instances[plugin_id] = instance
            return instance
        except Exception as e:
            print(f"Error loading plugin {plugin_id}: {e}")
            return None
    
    async def unload_plugin(self, plugin_id: str) -> bool:
        """
        Unload a plugin.
        
        Args:
            plugin_id: The ID of the plugin
            
        Returns:
            True if unloaded successfully, False otherwise
        """
        if plugin_id in self._plugins:  # FIXED: Check _plugins, not _instances
            del self._plugins[plugin_id]
            # Also remove instance if loaded
            if plugin_id in self._instances:
                del self._instances[plugin_id]
            return True
        return False
    
    def register_plugin(self, manifest: PluginManifest) -> None:
        """
        Register a plugin manually.
        
        Args:
            manifest: The plugin manifest to register
        """
        self._plugins[manifest.id] = manifest
    
    def unregister_plugin(self, plugin_id: str) -> bool:
        """
        Unregister a plugin.
        
        Args:
            plugin_id: The ID of the plugin to unregister
            
        Returns:
            True if unregistered successfully, False otherwise
        """
        if plugin_id in self._plugins:
            del self._plugins[plugin_id]
            # Also remove instance if loaded
            if plugin_id in self._instances:
                del self._instances[plugin_id]
            return True
        return False
