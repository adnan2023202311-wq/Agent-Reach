"""
In-memory capability registry implementation.

This is the reference implementation of the Registry interface.
It stores all capabilities in memory (no persistence yet).
"""

from __future__ import annotations

from typing import Any, List, Optional

from .interfaces import Registry
from .models import CapabilityMetadata, CapabilityType


class InMemoryRegistry(Registry):
    """
    In-memory implementation of the Registry interface.

    Stores all capabilities in a dictionary keyed by capability ID.
    This implementation is suitable for:
    - Development and testing
    - Single-process deployments
    - Cases where persistence is not required

    For production use with persistence, implement a PersistentRegistry
    that stores capabilities in a database or file system.
    """

    def __init__(self) -> None:
        """Initialize the registry with an empty capability store."""
        self._capabilities: dict[str, CapabilityMetadata] = {}

    def register(self, metadata: CapabilityMetadata) -> None:
        """
        Register a new capability.

        Args:
            metadata: The capability metadata to register

        Raises:
            RegistryError: If a capability with the same ID already exists
        """
        if metadata.id in self._capabilities:
            raise RegistryError(
                f"Capability with ID '{metadata.id}' is already registered"
            )

        # Validate dependencies exist
        for dep_id in metadata.dependencies:
            if dep_id not in self._capabilities:
                raise RegistryError(
                    f"Dependency '{dep_id}' not found for capability '{metadata.id}'"
                )

        self._capabilities[metadata.id] = metadata

    def unregister(self, capability_id: str) -> None:
        """
        Unregister a capability.

        Args:
            capability_id: The ID of the capability to unregister

        Raises:
            RegistryError: If no capability with the given ID exists
        """
        if capability_id not in self._capabilities:
            raise RegistryError(
                f"Capability with ID '{capability_id}' is not registered"
            )

        # Check if any other capability depends on this one
        for cap_id, cap in self._capabilities.items():
            if capability_id in cap.dependencies:
                raise RegistryError(
                    f"Cannot unregister capability '{capability_id}': "
                    f"capability '{cap_id}' depends on it"
                )

        del self._capabilities[capability_id]

    def get(self, capability_id: str) -> Optional[CapabilityMetadata]:
        """
        Get a capability by ID.

        Args:
            capability_id: The ID of the capability to retrieve

        Returns:
            The capability metadata, or None if not found
        """
        return self._capabilities.get(capability_id)

    def exists(self, capability_id: str) -> bool:
        """
        Check if a capability exists.

        Args:
            capability_id: The ID of the capability to check

        Returns:
            True if the capability exists, False otherwise
        """
        return capability_id in self._capabilities

    def list(self) -> List[CapabilityMetadata]:
        """
        List all registered capabilities.

        Returns:
            List of all capability metadata
        """
        return list(self._capabilities.values())

    def list_by_type(self, capability_type: CapabilityType) -> List[CapabilityMetadata]:
        """
        List capabilities by type.

        Args:
            capability_type: The type of capabilities to list

        Returns:
            List of capability metadata matching the given type
        """
        return [
            cap for cap in self._capabilities.values()
            if cap.type == capability_type
        ]

    def clear(self) -> None:
        """Clear all registered capabilities. Useful for testing."""
        self._capabilities.clear()


class RegistryError(Exception):
    """Exception raised for registry-related errors."""

    pass
