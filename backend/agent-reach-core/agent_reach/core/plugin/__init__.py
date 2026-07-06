"""
Plugin system package.

Provides plugin manifest models, loader interfaces, and static loader.
"""

from .loader_interfaces import PluginLoader
from .manifest import PluginManifest
from .static_loader import StaticPluginLoader

__all__ = [
    "PluginLoader",
    "PluginManifest",
    "StaticPluginLoader",
]
