"""
Milestone 2 Integration Tests.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from typing import Any

import pytest

from agent_reach.core.contracts.models import Contract, ContractStatus, ContractType
from agent_reach.core.contracts.registry import InMemoryContractRegistry
from agent_reach.core.engine.events import EventBus
from agent_reach.core.engine.executor import ExecutionEngine
from agent_reach.core.plugin.dynamic_loader import DynamicPluginLoader
from agent_reach.core.plugin.manager import PluginManager
from agent_reach.core.plugin.static_loader import StaticPluginLoader
from agent_reach.core.registry.models import CapabilityType
from agent_reach.core.registry.registry import InMemoryRegistry


class EchoPlugin:
    async def execute(self, input_data: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"echo": input_data.get("message", "")}


class CalculatorPlugin:
    async def execute(self, input_data: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        op = input_data.get("operation")
        a = input_data.get("a", 0)
        b = input_data.get("b", 0)
        if op == "add":
            return {"result": a + b}
        elif op == "multiply":
            return {"result": a * b}
        return {"error": "unknown operation"}


async def test_full_m2_workflow_with_static_loader() -> None:
    loader = StaticPluginLoader()
    registry = InMemoryRegistry()
    contract_registry = InMemoryContractRegistry()
    event_bus = EventBus()

    manager = PluginManager(
        loader=loader,
        registry=registry,
        contract_registry=contract_registry,
        event_bus=event_bus,
    )

    from agent_reach.core.plugin.manifest import PluginManifest
    loader.register_plugin(PluginManifest(
        id="plugin.echo.v1",
        name="Echo Plugin",
        version="1.0.0",
        description="Echoes input back",
        type="tool",
        entry_point="tests.test_m2_integration:EchoPlugin",
    ))

    discovered = await manager.discover()
    assert "plugin.echo.v1" in discovered

    errors = await manager.load("plugin.echo.v1")
    assert errors == []
    assert registry.exists("plugin.echo.v1")

    input_contract = Contract(
        id="contract.echo.input",
        name="Echo Input",
        version="1.0.0",
        type=ContractType.INPUT,
        status=ContractStatus.ACTIVE,
        plugin_id="plugin.echo.v1",
        schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
        },
    )
    errors = await manager.register_contract(input_contract)
    assert errors == []

    output_contract = Contract(
        id="contract.echo.output",
        name="Echo Output",
        version="1.0.0",
        type=ContractType.OUTPUT,
        status=ContractStatus.ACTIVE,
        plugin_id="plugin.echo.v1",
        schema={
            "type": "object",
            "properties": {
                "echo": {"type": "string"},
            },
            "required": ["echo"],
        },
    )
    errors = await manager.register_contract(output_contract)
    assert errors == []

    result = await manager.execute("plugin.echo.v1", {"message": "hello"})
    assert result.success is True
    assert result.output == {"echo": "hello"}

    result = await manager.execute("plugin.echo.v1", {})
    assert result.success is False
    assert any("message" in e for e in result.errors)

    errors = await manager.unload("plugin.echo.v1")
    assert errors == []
    assert not registry.exists("plugin.echo.v1")


async def test_full_m2_workflow_with_dynamic_loader() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = os.path.join(tmpdir, "calculator")
        os.makedirs(plugin_dir)
        manifest = {
            "id": "plugin.calculator.v1",
            "name": "Calculator",
            "version": "1.0.0",
            "description": "Simple calculator",
            "type": "tool",
            "entry_point": "tests.test_m2_integration:CalculatorPlugin",
        }
        with open(os.path.join(plugin_dir, "plugin.json"), "w") as f:
            json.dump(manifest, f)

        loader = DynamicPluginLoader(tmpdir)
        registry = InMemoryRegistry()
        contract_registry = InMemoryContractRegistry()
        event_bus = EventBus()

        manager = PluginManager(
            loader=loader,
            registry=registry,
            contract_registry=contract_registry,
            event_bus=event_bus,
        )

        discovered = await manager.discover()
        assert "plugin.calculator.v1" in discovered

        errors = await manager.load("plugin.calculator.v1")
        assert errors == []

        contract = Contract(
            id="contract.calc.input",
            name="Calc Input",
            version="1.0.0",
            type=ContractType.INPUT,
            status=ContractStatus.ACTIVE,
            plugin_id="plugin.calculator.v1",
            schema={
                "type": "object",
                "properties": {
                    "operation": {"type": "string"},
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
                "required": ["operation", "a", "b"],
            },
        )
        await manager.register_contract(contract)

        result = await manager.execute("plugin.calculator.v1", {"operation": "add", "a": 2, "b": 3})
        assert result.success is True
        assert result.output == {"result": 5}

        tools = manager.list_capabilities_by_type(CapabilityType.TOOL)
        assert len(tools) == 1
        assert tools[0].id == "plugin.calculator.v1"


async def test_m2_event_flow() -> None:
    loader = StaticPluginLoader()
    registry = InMemoryRegistry()
    contract_registry = InMemoryContractRegistry()
    event_bus = EventBus()

    manager = PluginManager(
        loader=loader,
        registry=registry,
        contract_registry=contract_registry,
        event_bus=event_bus,
    )

    events: list[dict[str, Any]] = []
    async def handler(event_type: str, payload: dict[str, Any]) -> None:
        events.append({"type": event_type, "payload": payload})

    event_bus.subscribe("plugin.loaded", handler)
    event_bus.subscribe("plugin.execution.succeeded", handler)
    event_bus.subscribe("plugin.unloaded", handler)

    from agent_reach.core.plugin.manifest import PluginManifest
    loader.register_plugin(PluginManifest(
        id="plugin.echo.v1",
        name="Echo",
        version="1.0.0",
        description="Echo",
        type="tool",
        entry_point="tests.test_m2_integration:EchoPlugin",
    ))

    await manager.load("plugin.echo.v1")
    await manager.execute("plugin.echo.v1", {"message": "hi"})
    await manager.unload("plugin.echo.v1")

    assert len(events) == 3
    assert events[0]["type"] == "plugin.loaded"
    assert events[1]["type"] == "plugin.execution.succeeded"
    assert events[2]["type"] == "plugin.unloaded"
