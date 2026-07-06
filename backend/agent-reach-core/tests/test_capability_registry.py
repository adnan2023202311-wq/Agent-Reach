"""
Tests for the Capability Registry.

Test the InMemoryRegistry implementation.
"""

import pytest
from datetime import datetime

from agent_reach.core.registry import (
    CapabilityMetadata,
    CapabilityType,
    InMemoryRegistry,
    RegistryError,
)


def test_register_capability() -> None:
    """Test registering a capability."""
    registry = InMemoryRegistry()
    
    metadata = CapabilityMetadata(
        id="agent.research.v1",
        name="Research Agent",
        version="1.0.0",
        type=CapabilityType.AGENT,
        description="Agent for researching",
    )
    
    registry.register(metadata)
    assert len(registry.list()) == 1


def test_register_duplicate_capability() -> None:
    """Test that registering duplicate capability raises error."""
    registry = InMemoryRegistry()
    
    metadata = CapabilityMetadata(
        id="agent.research.v1",
        name="Research Agent",
        version="1.0.0",
        type=CapabilityType.AGENT,
    )
    
    registry.register(metadata)
    
    with pytest.raises(RegistryError):
        registry.register(metadata)


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
    assert len(registry.list()) == 1
    
    registry.unregister("agent.research.v1")
    assert len(registry.list()) == 0


def test_get_capability() -> None:
    """Test getting a capability by ID."""
    registry = InMemoryRegistry()
    
    metadata = CapabilityMetadata(
        id="agent.research.v1",
        name="Research Agent",
        version="1.0.0",
        type=CapabilityType.AGENT,
    )
    
    registry.register(metadata)
    
    retrieved = registry.get("agent.research.v1")
    assert retrieved is not None
    assert retrieved.id == "agent.research.v1"
    assert retrieved.name == "Research Agent"


def test_list_by_type() -> None:
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


def test_dependency_validation() -> None:
    """Test that dependencies are validated on registration."""
    registry = InMemoryRegistry()
    
    # Register provider first
    provider = CapabilityMetadata(
        id="provider.anthropic.v1",
        name="Anthropic Provider",
        version="1.0.0",
        type=CapabilityType.PROVIDER,
    )
    registry.register(provider)
    
    # Register agent with dependency
    agent = CapabilityMetadata(
        id="agent.research.v1",
        name="Research Agent",
        version="1.0.0",
        type=CapabilityType.AGENT,
        dependencies=["provider.anthropic.v1"],
    )
    registry.register(agent)  # Should succeed
    
    # Try to unregister provider (should fail because agent depends on it)
    with pytest.raises(RegistryError):
        registry.unregister("provider.anthropic.v1")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
