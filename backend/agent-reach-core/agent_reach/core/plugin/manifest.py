"""
Plugin manifest models for Agent Reach.

Defines the structure for plugin manifest files (plugin.json).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginManifest:
    """
    Manifest metadata for a plugin.
    
    This corresponds to the plugin.json file that each plugin must provide.
    
    Attributes:
        id: Unique plugin identifier (e.g., "agent.research.v1")
        name: Human-readable plugin name
        version: Semantic version
        description: What this plugin does
        type: Plugin type (agent, provider, tool, planner, memory, workflow)
        author: Plugin author/team
        homepage: URL for documentation/source
        capabilities: List of capabilities this plugin provides
        dependencies: List of plugin IDs this plugin depends on
        entry_point: Python module:class path for the plugin
        config_schema: JSON schema for plugin configuration (optional)
    """
    
    id: str
    name: str
    version: str
    description: str
    type: str
    author: str = ""
    homepage: str = ""
    capabilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    entry_point: str = ""
    config_schema: dict[str, Any] | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "type": self.type,
            "author": self.author,
            "homepage": self.homepage,
            "capabilities": self.capabilities,
            "dependencies": self.dependencies,
            "entry_point": self.entry_point,
            "config_schema": self.config_schema,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        """Create from dictionary (loaded from plugin.json)."""
        return cls(**data)
