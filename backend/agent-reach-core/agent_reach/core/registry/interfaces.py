"""
Registry interface for capability registration and discovery.

Defines the contract that all registry implementations must fulfill.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, List

from .models import CapabilityMetadata, CapabilityType


class Registry(Any):
    """
    Interface for the capability registry.

    The registry is responsible for:
    - Registering new capabilities
    - Unregistering existing capabilities
    - Retrieving capability metadata
    - Listing capabilities by type
    """

    @abstractmethod
    def register(self, metadata: CapabilityMetadata) -> None:
        """
        Register a new capability.

        Args:
            metadata: The capability metadata to register

        Raises:
            RegistryError: If a capability with the same ID already exists
        """
        ...

    @abstractmethod
    def unregister(self, capability_id: str) -> None:
        """
        Unregister a capability.

        Args:
            capability_id: The ID of the capability to unregister

        Raises:
            RegistryError: If no capability with the given ID exists
        """
        ...

    @abstractmethod
    def get(self, capability_id: str) -> CapabilityMetadata | None:
        """
        Get a capability by ID.

        Args:
            capability_id: The ID of the capability to retrieve

        Returns:
            The capability metadata, or None if not found
        """
        ...

    @abstractmethod
    def exists(self, capability_id: str) -> bool:
        """
        Check if a capability exists.

        Args:
            capability_id: The ID of the capability to check

        Returns:
            True if the capability exists, False otherwise
        """
        ...

    @abstractmethod
    def list(self) -> List[CapabilityMetadata]:
        """
        List all registered capabilities.

        Returns:
            List of all capability metadata
        """
        ...

    @abstractmethod
    def list_by_type(self, capability_type: CapabilityType) -> List[CapabilityMetadata]:
        """
        List capabilities by type.

        Args:
            capability_type: The type of capabilities to list

        Returns:
            List of capability metadata matching the given type
        """
        ...
