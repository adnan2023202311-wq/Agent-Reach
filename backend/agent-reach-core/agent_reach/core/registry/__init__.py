"""
Capability Registry package.

Provides a registry for registering and discovering capabilities:
- Agents
- Providers
- Tools
- Planners
- Memory systems
- Workflows
"""

from .interfaces import Registry
from .models import CapabilityMetadata, CapabilityType
from .registry import InMemoryRegistry, RegistryError

__all__ = [
    # Interfaces
    "Registry",
    # Models
    "CapabilityMetadata",
    "CapabilityType",
    # Implementations
    "InMemoryRegistry",
    # Exceptions
    "RegistryError",
]
