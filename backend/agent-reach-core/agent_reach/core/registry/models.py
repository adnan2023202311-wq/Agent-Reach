"""
Capability metadata models for the registry.

Defines the structure for all capability types:
- Agent
- Provider
- Tool
- Planner
- Memory
- Workflow
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class CapabilityType(str, Enum):
    """Types of capabilities that can be registered."""

    AGENT = "agent"
    PROVIDER = "provider"
    TOOL = "tool"
    PLANNER = "planner"
    MEMORY = "memory"
    WORKFLOW = "workflow"


@dataclass
class CapabilityMetadata:
    """
    Metadata for a registered capability.

    Attributes:
        id: Unique identifier for the capability
        name: Human-readable name
        version: Semantic version (e.g., "1.0.0")
        type: The capability type
        description: What this capability does
        capabilities: List of capabilities this capability provides
        dependencies: List of capability IDs this depends on
        enabled: Whether this capability is currently enabled
        registered_at: When the capability was registered
        metadata: Additional type-specific metadata
    """

    id: str
    name: str
    version: str
    type: CapabilityType
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    enabled: bool = True
    registered_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "type": self.type.value,
            "description": self.description,
            "capabilities": self.capabilities,
            "dependencies": self.dependencies,
            "enabled": self.enabled,
            "registered_at": self.registered_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CapabilityMetadata:
        """Create from dictionary."""
        data = data.copy()
        data["type"] = CapabilityType(data["type"])
        data["registered_at"] = datetime.fromisoformat(data["registered_at"])
        return cls(**data)
