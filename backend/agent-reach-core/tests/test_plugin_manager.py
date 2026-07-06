"""
Tests for the Plugin Manager.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent_reach.core.contracts.models import Contract, ContractStatus, ContractType
from agent_reach.core.contracts.registry import InMemoryContractRegistry
from agent_reach.core.engine.events import EventBus
from agent_reach.core.plugin.manager import PluginManager
from agent_reach.core.plugin.manifest import PluginManifest
from agent_reach.core.plugin.static_loader import StaticPluginLoader
from agent_reach.core.registry.models import CapabilityType
from agent_reach.core.registry.registry import InMemoryRegistry


class FakePlugin:
    async def execute(self, input_data: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"result": "ok"}


@pytest.fixture
def manager() -> PluginManager:
    loader = StaticPluginLoader()
    registry = InMemoryRegistry()
    contract_registry = InMemoryContractRegistry()
    event_bus = EventBus()
    return PluginManager(
        loader=loader,
        registry=registry,
        contract_registry=contract_registry,
        event_bus=event_bus,
    )


async def test_discover(manager: PluginManager) -> None:
    loader = manager._loader
    assert isinstance(loader, StaticPluginLoader)
    loader.register_plugin(PluginManifest(
        id="agent.test.v1",
        name="Test Agent",
        version="1.0.0",
        description="Test",
        type="agent",
    ))

    plugins = await manager.discover()
    assert "agent.test.v1" in plugins


async def test_load_and_register_capability(manager: PluginManager) -> None:
    manifest = PluginManifest(
        id="agent.test.v1",
        name="Test Agent",
        version="1.0.0",
        description="Test",
        type="agent",
        capabilities=["test"],
    )
    manager._loader.register_plugin(manifest)

    errors = await manager.load("agent.test.v1")
    assert errors == []

    capability = manager._registry.get("agent.test.v1")
    assert capability is not None
    assert capability.name == "Test Agent"
    assert capability.type.value == "agent"


async def test_load_with_invalid_config(manager: PluginManager) -> None:
    manifest = PluginManifest(
        id="agent.test.v1",
        name="Test Agent",
        version="1.0.0",
        description="Test",
        type="agent",
        config_schema={
            "type": "object",
            "required": ["api_key"],
            "properties": {
                "api_key": {"type": "string"},
            },
        },
    )
    manager._loader.register_plugin(manifest)

    errors = await manager.load("agent.test.v1", config={})
    assert len(errors) == 1
    assert "api_key" in errors[0]


async def test_load_event(manager: PluginManager) -> None:
    events: list[dict[str, Any]] = []
    async def handler(event_type: str, payload: dict[str, Any]) -> None:
        events.append(payload)
    manager._event_bus.subscribe("plugin.loaded", handler)

    manifest = PluginManifest(
        id="agent.test.v1",
        name="Test Agent",
        version="1.0.0",
        description="Test",
        type="agent",
    )
    manager._loader.register_plugin(manifest)
    await manager.load("agent.test.v1")

    assert len(events) == 1
    assert events[0]["plugin_id"] == "agent.test.v1"


async def test_unload(manager: PluginManager) -> None:
    manifest = PluginManifest(
        id="agent.test.v1",
        name="Test Agent",
        version="1.0.0",
        description="Test",
        type="agent",
    )
    manager._loader.register_plugin(manifest)
    await manager.load("agent.test.v1")
    assert manager._registry.exists("agent.test.v1")

    errors = await manager.unload("agent.test.v1")
    assert errors == []
    assert not manager._registry.exists("agent.test.v1")


async def test_execute(manager: PluginManager) -> None:
    manifest = PluginManifest(
        id="agent.test.v1",
        name="Test Agent",
        version="1.0.0",
        description="Test",
        type="agent",
        entry_point="tests.test_plugin_manager:FakePlugin",
    )
    manager._loader.register_plugin(manifest)
    await manager.load("agent.test.v1")

    result = await manager.execute("agent.test.v1", {"query": "test"})
    assert result.success is True
    assert result.output == {"result": "ok"}


async def test_register_contract(manager: PluginManager) -> None:
    contract = Contract(
        id="contract.test.v1",
        name="Test Contract",
        version="1.0.0",
        type=ContractType.INPUT,
        status=ContractStatus.ACTIVE,
        plugin_id="agent.test.v1",
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    )

    errors = await manager.register_contract(contract)
    assert errors == []

    retrieved = await manager._contract_registry.get("contract.test.v1")
    assert retrieved is not None


async def test_list_capabilities(manager: PluginManager) -> None:
    manifest = PluginManifest(
        id="agent.test.v1",
        name="Test Agent",
        version="1.0.0",
        description="Test",
        type="agent",
    )
    manager._loader.register_plugin(manifest)
    await manager.load("agent.test.v1")

    capabilities = manager.list_capabilities()
    assert len(capabilities) == 1
    assert capabilities[0].id == "agent.test.v1"


async def test_list_capabilities_by_type(manager: PluginManager) -> None:
    agent_manifest = PluginManifest(
        id="agent.test.v1",
        name="Test Agent",
        version="1.0.0",
        description="Test",
        type="agent",
    )
    provider_manifest = PluginManifest(
        id="provider.test.v1",
        name="Test Provider",
        version="1.0.0",
        description="Test",
        type="provider",
    )
    manager._loader.register_plugin(agent_manifest)
    manager._loader.register_plugin(provider_manifest)
    await manager.load("agent.test.v1")
    await manager.load("provider.test.v1")

    agents = manager.list_capabilities_by_type(CapabilityType.AGENT)
    providers = manager.list_capabilities_by_type(CapabilityType.PROVIDER)

    assert len(agents) == 1
    assert len(providers) == 1
