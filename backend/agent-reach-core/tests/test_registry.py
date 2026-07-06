"""
Unit tests for the Capability Registry.

Test the InMemoryRegistry implementation.
"""

from __future__ import annotations

import pytest
from datetime import datetime

from agent_reach.core.registry import (
    CapabilityMetadata,
    CapabilityType,
    InMemoryRegistry,
    RegistryError,
)


def test_register_and_get_capability() -> None:
    """Test registering and retrieving a capability."""
    registry = InMemoryRegistry()

    metadata = CapabilityMetadata(
        id="agent.research.v1",
        name="Research Agent",
        version="1.0.0",
        type=CapabilityType.AGENT,
        description="Agent for researching information",
        capabilities=["search", "summarize"],
    )

    registry.register(metadata)

    retrieved = registry.get("agent.research.v1")
    assert retrieved is not None
    assert retrieved.id == "agent.research.v1"
    assert retrieved.name == "Research Agent"
    assert retrieved.type == CapabilityType.AGENT


def test_register_duplicate_capability() -> None:
    """Test that registering a duplicate capability raises an error."""
    registry = InMemoryRegistry()

    metadata = CapabilityMetadata(
        id="agent.research.v1",
        name="Research Agent",
        version="1.0.0",
        type=CapabilityType.AGENT,
    )

    registry.register(metadata)

    with pytest.raises(RegistryError) as exc_info:
        registry.register(metadata)

    assert "already registered" in str(exc_info.value)


def test_unregister_capability() -> None:
    """Test unregistering a capability."""
    registry = InMemoryRegistry()

    metadata = CapabilityMetadata(
        id="agent.research.v1",
        name="Research Agent",
        version="1.0.0",
        type=CapabilityType.AGENT,
    )

    registry.register(metadata)
    assert registry.exists("agent.research.v1")

    registry.unregister("agent.research.v1")
    assert not registry.exists("agent.research.v1")
    assert registry.get("agent.research.v1") is None


def test_unregister_nonexistent_capability() -> None:
    """Test that unregistering a non-existent capability raises an error."""
    registry = InMemoryRegistry()

    with pytest.raises(RegistryError) as exc_info:
        registry.unregister("nonexistent")

    assert "not registered" in str(exc_info.value)


def test_unregister_capability_with_dependents() -> None:
    """Test that unregistering a capability with dependents raises an error."""
    registry = InMemoryRegistry()

    # Register a provider
    provider = CapabilityMetadata(
        id="provider.anthropic.v1",
        name="Anthropic Provider",
        version="1.0.0",
        type=CapabilityType.PROVIDER,
    )
    registry.register(provider)

    # Register an agent that depends on the provider
    agent = CapabilityMetadata(
        id="agent.research.v1",
        name="Research Agent",
        version="1.0.0",
        type=CapabilityType.AGENT,
        dependencies=["provider.anthropic.v1"],
    )
    registry.register(agent)

    # Try to unregister the provider (should fail)
    with pytest.raises(RegistryError) as exc_info:
        registry.unregister("provider.anthropic.v1")

    assert "depends on it" in str(exc_info.value)


def test_exists_capability() -> None:
    """Test checking if a capability exists."""
    registry = InMemoryRegistry()

    metadata = CapabilityMetadata(
        id="agent.research.v1",
        name="Research Agent",
        version="1.0.0",
        type=CapabilityType.AGENT,
    )

    assert not registry.exists("agent.research.v1")

    registry.register(metadata)

    assert registry.exists("agent.research.v1")


def test_list_all_capabilities() -> None:
    """Test listing all capabilities."""
    registry = InMemoryRegistry()

    agent = CapabilityMetadata(
        id="agent.research.v1",
        name="Research Agent",
        version="1.0.0",
        type=CapabilityType.AGENT,
    )

    provider = CapabilityMetadata(
        id="provider.anthropic.v1",
        name="Anthropic Provider",
        version="1.0.0",
        type=CapabilityType.PROVIDER,
    )

    registry.register(agent)
    registry.register(provider)

    all_caps = registry.list()
    assert len(all_caps) == 2


def test_list_capabilities_by_type() -> None:
    """Test listing capabilities by type."""
    registry = InMemoryRegistry()

    agent1 = CapabilityMetadata(
        id="agent.research.v1",
        name="Research Agent",
        version="1.0.0",
        type=CapabilityType.AGENT,
    )

    agent2 = CapabilityMetadata(
        id="agent.coding.v1",
        name="Coding Agent",
        version="1.0.0",
        type=CapabilityType.AGENT,
    )

    provider = CapabilityMetadata(
        id="provider.anthropic.v1",
        name="Anthropic Provider",
        version="1.0.0",
        type=CapabilityType.PROVIDER,
    )

    registry.register(agent1)
    registry.register(agent2)
    registry.register(provider)

    agents = registry.list_by_type(CapabilityType.AGENT)
    assert len(agents) == 2

    providers = registry.list_by_type(CapabilityType.PROVIDER)
    assert len(providers) == 1


def test_register_capability_with_invalid_dependency() -> None:
    """Test that registering a capability with invalid dependencies raises an error."""
    registry = InMemoryRegistry()

    agent = CapabilityMetadata(
        id="agent.research.v1",
        name="Research Agent",
        version="1.0.0",
        type=CapabilityType.AGENT,
        dependencies=["nonexistent.provider"],
    )

    with pytest.raises(RegistryError) as exc_info:
        registry.register(agent)

    assert "not found" in str(exc_info.value)


def test_capability_metadata_to_dict() -> None:
    """Test converting CapabilityMetadata to dictionary."""
    metadata = CapabilityMetadata(
        id="agent.research.v1",
        name="Research Agent",
        version="1.0.0",
        type=CapabilityType.AGENT,
        description="Agent for researching",
        capabilities=["search", "summarize"],
        dependencies=["provider.anthropic.v1"],
        enabled=True,
    )

    data = metadata.to_dict()

    assert data["id"] == "agent.research.v1"
    assert data["type"] == "agent"
    assert "registered_at" in data


def test_clear_registry() -> None:
    """Test clearing the registry."""
    registry = InMemoryRegistry()

    metadata = CapabilityMetadata(
        id="agent.research.v1",
        name="Research Agent",
        version="1.0.0",
        type=CapabilityType.AGENT,
    )

    registry.register(metadata)
    assert len(registry.list()) == 1

    registry.clear()
    assert len(registry.list()) == 0
