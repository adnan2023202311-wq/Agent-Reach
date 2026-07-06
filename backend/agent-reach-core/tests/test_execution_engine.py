"""
Tests for the Execution Engine.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent_reach.core.contracts.models import Contract, ContractStatus, ContractType
from agent_reach.core.contracts.registry import InMemoryContractRegistry
from agent_reach.core.engine.events import EventBus
from agent_reach.core.engine.executor import ExecutionEngine, ExecutionResult
from agent_reach.core.plugin.manifest import PluginManifest
from agent_reach.core.plugin.static_loader import StaticPluginLoader


class FakePlugin:
    async def execute(self, input_data: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"result": f"processed: {input_data.get('query', '')}"}


class BadPlugin:
    async def execute(self, input_data: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        raise RuntimeError("plugin error")


class NoExecutePlugin:
    pass


@pytest.fixture
def loader() -> StaticPluginLoader:
    return StaticPluginLoader()


@pytest.fixture
def contract_registry() -> InMemoryContractRegistry:
    return InMemoryContractRegistry()


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def engine(
    loader: StaticPluginLoader,
    contract_registry: InMemoryContractRegistry,
    event_bus: EventBus,
) -> ExecutionEngine:
    return ExecutionEngine(
        loader=loader,
        contract_registry=contract_registry,
        event_bus=event_bus,
    )


async def test_execute_success(
    loader: StaticPluginLoader,
    contract_registry: InMemoryContractRegistry,
    engine: ExecutionEngine,
) -> None:
    manifest = PluginManifest(
        id="plugin.fake.v1",
        name="Fake Plugin",
        version="1.0.0",
        description="Test",
        type="agent",
        entry_point="tests.test_execution_engine:FakePlugin",
    )
    loader.register_plugin(manifest)

    result = await engine.execute("plugin.fake.v1", {"query": "test"})

    assert result.success is True
    assert result.plugin_id == "plugin.fake.v1"
    assert result.output == {"result": "processed: test"}
    assert result.errors == []
    assert result.duration_ms >= 0


async def test_execute_plugin_not_found(
    engine: ExecutionEngine,
) -> None:
    result = await engine.execute("nonexistent", {})

    assert result.success is False
    assert "not found" in result.errors[0]


async def test_execute_no_execute_method(
    loader: StaticPluginLoader,
    contract_registry: InMemoryContractRegistry,
    engine: ExecutionEngine,
) -> None:
    manifest = PluginManifest(
        id="plugin.noexecute.v1",
        name="No Execute Plugin",
        version="1.0.0",
        description="Test",
        type="agent",
        entry_point="tests.test_execution_engine:NoExecutePlugin",
    )
    loader.register_plugin(manifest)

    result = await engine.execute("plugin.noexecute.v1", {})

    assert result.success is False
    assert "does not have a callable execute method" in result.errors[0]


async def test_execute_plugin_raises(
    loader: StaticPluginLoader,
    contract_registry: InMemoryContractRegistry,
    engine: ExecutionEngine,
    event_bus: EventBus,
) -> None:
    manifest = PluginManifest(
        id="plugin.bad.v1",
        name="Bad Plugin",
        version="1.0.0",
        description="Test",
        type="agent",
        entry_point="tests.test_execution_engine:BadPlugin",
    )
    loader.register_plugin(manifest)

    events: list[dict[str, Any]] = []
    async def handler(event_type: str, payload: dict[str, Any]) -> None:
        events.append(payload)
    event_bus.subscribe("plugin.execution.failed", handler)

    result = await engine.execute("plugin.bad.v1", {})

    assert result.success is False
    assert "Execution failed" in result.errors[0]
    assert len(events) == 1
    assert events[0]["plugin_id"] == "plugin.bad.v1"


async def test_execute_with_input_contract_validation(
    loader: StaticPluginLoader,
    contract_registry: InMemoryContractRegistry,
    engine: ExecutionEngine,
) -> None:
    manifest = PluginManifest(
        id="plugin.contract.v1",
        name="Contract Plugin",
        version="1.0.0",
        description="Test",
        type="agent",
        entry_point="tests.test_execution_engine:FakePlugin",
    )
    loader.register_plugin(manifest)

    contract = Contract(
        id="contract.input.v1",
        name="Input Contract",
        version="1.0.0",
        type=ContractType.INPUT,
        status=ContractStatus.ACTIVE,
        plugin_id="plugin.contract.v1",
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    )
    await contract_registry.register(contract)

    result = await engine.execute("plugin.contract.v1", {})
    assert result.success is False
    assert any("query" in e for e in result.errors)

    result = await engine.execute("plugin.contract.v1", {"query": "test"})
    assert result.success is True


async def test_execute_with_output_contract_validation(
    loader: StaticPluginLoader,
    contract_registry: InMemoryContractRegistry,
    engine: ExecutionEngine,
) -> None:
    manifest = PluginManifest(
        id="plugin.output.v1",
        name="Output Plugin",
        version="1.0.0",
        description="Test",
        type="agent",
        entry_point="tests.test_execution_engine:FakePlugin",
    )
    loader.register_plugin(manifest)

    contract = Contract(
        id="contract.output.v1",
        name="Output Contract",
        version="1.0.0",
        type=ContractType.OUTPUT,
        status=ContractStatus.ACTIVE,
        plugin_id="plugin.output.v1",
        schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
            },
            "required": ["result"],
        },
    )
    await contract_registry.register(contract)

    result = await engine.execute("plugin.output.v1", {"query": "test"})
    assert result.success is True
    assert result.output == {"result": "processed: test"}


async def test_execute_success_event(
    loader: StaticPluginLoader,
    contract_registry: InMemoryContractRegistry,
    engine: ExecutionEngine,
    event_bus: EventBus,
) -> None:
    manifest = PluginManifest(
        id="plugin.event.v1",
        name="Event Plugin",
        version="1.0.0",
        description="Test",
        type="agent",
        entry_point="tests.test_execution_engine:FakePlugin",
    )
    loader.register_plugin(manifest)

    events: list[dict[str, Any]] = []
    async def handler(event_type: str, payload: dict[str, Any]) -> None:
        events.append(payload)
    event_bus.subscribe("plugin.execution.succeeded", handler)

    result = await engine.execute("plugin.event.v1", {"query": "test"})

    assert result.success is True
    assert len(events) == 1
    assert events[0]["plugin_id"] == "plugin.event.v1"
