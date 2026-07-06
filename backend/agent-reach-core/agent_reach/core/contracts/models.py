"""
Contract models for Agent Reach.

Defines the structure for plugin contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ContractType(str, Enum):
    """Types of contracts."""
    
    INPUT = "input"
    OUTPUT = "output"
    CONFIG = "config"
    SCHEMA = "schema"


class ContractStatus(str, Enum):
    """Status of a contract."""
    
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    REJECTED = "rejected"


@dataclass
class Contract:
    """
    A contract defines the expected input/output for a plugin.
    
    Attributes:
        id: Unique contract identifier
        name: Human-readable name
        version: Semantic version
        type: Contract type (input/output/config/schema)
        status: Contract status
        plugin_id: The plugin this contract belongs to
        schema: JSON schema for validation
        description: What this contract defines
        created_at: When the contract was created
        updated_at: When the contract was last updated
    """
    
    id: str
    name: str
    version: str
    type: ContractType
    status: ContractStatus
    plugin_id: str
    schema: dict[str, Any]
    description: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "type": self.type.value,
            "status": self.status.value,
            "plugin_id": self.plugin_id,
            "schema": self.schema,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Contract:
        """Create from dictionary."""
        data = data.copy()
        data["type"] = ContractType(data["type"])
        data["status"] = ContractStatus(data["status"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)
