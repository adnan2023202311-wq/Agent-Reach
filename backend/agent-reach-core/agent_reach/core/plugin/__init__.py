"""
Plugin system package.

Provides plugin manifest models and loader interfaces.
"""

from .loader_interfaces import PluginLoader
from .manifest import PluginManifest

__all__ = [
    "PluginLoader",
    "PluginManifest",
]
