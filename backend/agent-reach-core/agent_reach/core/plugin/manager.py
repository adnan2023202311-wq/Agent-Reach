"""
Plugin manager for Agent Reach.

Orchestrates the full plugin lifecycle:
discover → load → validate contracts → register capabilities → execute → unload
"""

from __future__ import annotations

from typing import Any

from ..contracts.interfaces import ContractRegistry
from ..contracts.models import Contract, ContractStatus, ContractType
from ..contracts.validator import ContractValidator
from ..engine.events import EventBus
from ..registry.interfaces import Registry
from ..registry.models import CapabilityMetadata, CapabilityType
from ..schemas.resolver import SchemaResolver
from .config_validator import ConfigValidator
from .loader_interfaces import PluginLoader
from .manifest import PluginManifest


class PluginManager:
    """High-level orchestrator for the plugin system."""

    def __init__(
        self,
        loader: PluginLoader,
        registry: Registry,
        contract_registry: ContractRegistry,
        event_bus: EventBus | None = None,
        schema_resolver: SchemaResolver | None = None,
    ) -> None:
        self._loader = loader
        self._registry = registry
        self._contract_registry = contract_registry
        self._event_bus = event_bus
        self._config_validator = ConfigValidator(schema_resolver)
        # Lazy import to avoid circular dependency with engine.executor
        from ..engine.executor import ExecutionEngine
        self._execution_engine = ExecutionEngine(
            loader=loader,
            contract_registry=contract_registry,
            event_bus=event_bus,
        )

    async def discover(self) -> list[str]:
        """Discover available plugins."""
        return await self._loader.discover()

    async def load(
        self,
        plugin_id: str,
        config: dict[str, Any] | None = None,
    ) -> list[str]:
        """Load a plugin and register its capabilities and contracts."""
        errors: list[str] = []

        manifest = await self._loader.load_manifest(plugin_id)
        if manifest is None:
            errors.append(f"Plugin '{plugin_id}' not found")
            return errors

        if config is not None:
            config_errors = self._config_validator.validate(manifest, config)
            if config_errors:
                errors.extend(config_errors)
                return errors

        capability_type = self._map_plugin_type(manifest.type)
        capability = CapabilityMetadata(
            id=manifest.id,
            name=manifest.name,
            version=manifest.version,
            type=capability_type,
            description=manifest.description,
            capabilities=manifest.capabilities,
            dependencies=manifest.dependencies,
            enabled=True,
            metadata={
                "author": manifest.author,
                "homepage": manifest.homepage,
                "entry_point": manifest.entry_point,
                "config": config or {},
            },
        )

        try:
            self._registry.register(capability)
        except Exception as exc:
            errors.append(f"Failed to register capability: {exc}")
            return errors

        if self._event_bus:
            await self._event_bus.publish(
                "plugin.loaded",
                {"plugin_id": plugin_id, "name": manifest.name},
            )

        return errors

    async def unload(self, plugin_id: str) -> list[str]:
        """Unload a plugin and unregister its capabilities."""
        errors: list[str] = []

        try:
            self._registry.unregister(plugin_id)
        except Exception as exc:
            errors.append(f"Failed to unregister capability: {exc}")

        success = await self._loader.unload_plugin(plugin_id)
        if not success:
            errors.append(f"Plugin '{plugin_id}' could not be unloaded from loader")

        if self._event_bus and not errors:
            await self._event_bus.publish(
                "plugin.unloaded",
                {"plugin_id": plugin_id},
            )

        return errors

    async def execute(
        self,
        plugin_id: str,
        input_data: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a plugin with input/output validation."""
        return await self._execution_engine.execute(plugin_id, input_data, config)

    async def register_contract(self, contract: Contract) -> list[str]:
        """Register a contract for a plugin."""
        errors: list[str] = []
        try:
            await self._contract_registry.register(contract)
        except Exception as exc:
            errors.append(f"Failed to register contract: {exc}")
        return errors

    def list_capabilities(self) -> list[CapabilityMetadata]:
        """List all registered capabilities."""
        return self._registry.list()

    def list_capabilities_by_type(
        self,
        capability_type: CapabilityType,
    ) -> list[CapabilityMetadata]:
        """List capabilities by type."""
        return self._registry.list_by_type(capability_type)

    @staticmethod
    def _map_plugin_type(plugin_type: str) -> CapabilityType:
        """Map a plugin manifest type to a capability type."""
        mapping = {
            "agent": CapabilityType.AGENT,
            "provider": CapabilityType.PROVIDER,
            "tool": CapabilityType.TOOL,
            "planner": CapabilityType.PLANNER,
            "memory": CapabilityType.MEMORY,
            "workflow": CapabilityType.WORKFLOW,
        }
        return mapping.get(plugin_type, CapabilityType.TOOL)
