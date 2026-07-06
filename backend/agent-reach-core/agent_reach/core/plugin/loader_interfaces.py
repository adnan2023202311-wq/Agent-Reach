"""
Plugin loader interfaces for Agent Reach.

Defines the contract that all plugin loaders must fulfill.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from .manifest import PluginManifest


class PluginLoader(Any):
    """
    Interface for plugin loaders.
    
    Plugin loaders are responsible for:
    - Discovering plugins
    - Loading plugin manifests
    - Instantiating plugin classes
    """
    
    @abstractmethod
    async def discover(self) -> list[str]:
        """
        Discover available plugins.
        
        Returns:
            List of plugin IDs discovered
        """
        ...
    
    @abstractmethod
    async def load_manifest(self, plugin_id: str) -> PluginManifest | None:
        """
        Load a plugin's manifest.
        
        Args:
            plugin_id: The ID of the plugin
            
        Returns:
            The plugin manifest, or None if not found
        """
        ...
    
    @abstractmethod
    async def load_plugin(self, plugin_id: str) -> Any | None:
        """
        Load and instantiate a plugin.
        
        Args:
            plugin_id: The ID of the plugin
            
        Returns:
            The instantiated plugin object, or None if not found
        """
        ...
    
    @abstractmethod
    async def unload_plugin(self, plugin_id: str) -> bool:
        """
        Unload a plugin.
        
        Args:
            plugin_id: The ID of the plugin
            
        Returns:
            True if unloaded successfully, False otherwise
        """
        ...
