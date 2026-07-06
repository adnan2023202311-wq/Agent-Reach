"""
Plugin execution engine.

Executes plugins with input/output contract validation,
error handling, and result wrapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..contracts.interfaces import ContractRegistry
from ..contracts.models import ContractType
from ..contracts.validator import ContractValidator
from ..plugin.loader_interfaces import PluginLoader
from ..plugin.manifest import PluginManifest
from .events import EventBus


@dataclass
class ExecutionResult:
    """Result of executing a plugin."""

    plugin_id: str
    success: bool
    output: Any = None
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


class ExecutionEngine:
    """Executes plugins with contract validation."""

    def __init__(
        self,
        loader: PluginLoader,
        contract_registry: ContractRegistry,
        event_bus: EventBus | None = None,
    ) -> None:
        self._loader = loader
        self._contract_registry = contract_registry
        self._validator = ContractValidator(contract_registry)
        self._event_bus = event_bus

    async def execute(
        self,
        plugin_id: str,
        input_data: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute a plugin with input/output validation."""
        import time

        start = time.perf_counter()
        errors: list[str] = []

        manifest = await self._loader.load_manifest(plugin_id)
        if manifest is None:
            errors.append(f"Plugin '{plugin_id}' not found")
            return ExecutionResult(
                plugin_id=plugin_id,
                success=False,
                errors=errors,
                duration_ms=self._elapsed_ms(start),
            )

        input_contracts = await self._get_contracts(plugin_id, ContractType.INPUT)
        for contract in input_contracts:
            contract_errors = await self._validator.validate(contract.id, input_data)
            errors.extend(contract_errors)

        if errors:
            return ExecutionResult(
                plugin_id=plugin_id,
                success=False,
                errors=errors,
                duration_ms=self._elapsed_ms(start),
            )

        instance = await self._loader.load_plugin(plugin_id)
        if instance is None:
            errors.append(f"Plugin '{plugin_id}' could not be loaded")
            return ExecutionResult(
                plugin_id=plugin_id,
                success=False,
                errors=errors,
                duration_ms=self._elapsed_ms(start),
            )

        try:
            if hasattr(instance, "execute") and callable(getattr(instance, "execute")):
                kwargs: dict[str, Any] = {"input_data": input_data}
                if config is not None:
                    kwargs["config"] = config
                output = await instance.execute(**kwargs)
            else:
                errors.append(
                    f"Plugin '{plugin_id}' does not have a callable execute method"
                )
                return ExecutionResult(
                    plugin_id=plugin_id,
                    success=False,
                    errors=errors,
                    duration_ms=self._elapsed_ms(start),
                )
        except Exception as exc:
            errors.append(f"Execution failed: {exc}")
            if self._event_bus:
                await self._event_bus.publish(
                    "plugin.execution.failed",
                    {"plugin_id": plugin_id, "error": str(exc)},
                )
            return ExecutionResult(
                plugin_id=plugin_id,
                success=False,
                errors=errors,
                duration_ms=self._elapsed_ms(start),
            )

        if output is not None and isinstance(output, dict):
            output_contracts = await self._get_contracts(plugin_id, ContractType.OUTPUT)
            for contract in output_contracts:
                contract_errors = await self._validator.validate(contract.id, output)
                errors.extend(contract_errors)

        if errors:
            return ExecutionResult(
                plugin_id=plugin_id,
                success=False,
                errors=errors,
                duration_ms=self._elapsed_ms(start),
            )

        if self._event_bus:
            await self._event_bus.publish(
                "plugin.execution.succeeded",
                {"plugin_id": plugin_id, "output": output},
            )

        return ExecutionResult(
            plugin_id=plugin_id,
            success=True,
            output=output,
            duration_ms=self._elapsed_ms(start),
        )

    async def _get_contracts(
        self,
        plugin_id: str,
        contract_type: ContractType,
    ) -> list[Any]:
        """Get all contracts of a given type for a plugin."""
        contracts = await self._contract_registry.get_by_plugin(plugin_id)
        return [c for c in contracts if c.type == contract_type]

    @staticmethod
    def _elapsed_ms(start: float) -> float:
        import time
        return (time.perf_counter() - start) * 1000
