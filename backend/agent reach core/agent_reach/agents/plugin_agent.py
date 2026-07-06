"""
Agents layer: PluginAgent.

Layer: Adapters — implements domain.interfaces.Agent.

Bridges the plugin system (agent-reach-core) with the kernel's
Agent interface. Each PluginAgent wraps a plugin loaded through
the PluginManager and delegates execute() calls to it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure agent-reach-core is on the path so we can import the plugin system.
_ARK_CORE = Path(__file__).resolve().parent.parent.parent.parent / "agent-reach-core"
if str(_ARK_CORE) not in sys.path:
    sys.path.insert(0, str(_ARK_CORE))

from agent_reach.core.engine.executor import ExecutionEngine  # noqa: E402
from agent_reach.core.plugin.loader_interfaces import PluginLoader  # noqa: E402
from agent_reach.core.plugin.manager import PluginManager  # noqa: E402
from agent_reach.core.registry.interfaces import Registry  # noqa: E402
from agent_reach.core.registry.models import CapabilityType  # noqa: E402

from domain.interfaces import Agent  # noqa: E402
from domain.models import AgentType, SubTask  # noqa: E402


class PluginAgent(Agent):
    """Kernel agent that delegates to a plugin from the plugin system."""

    def __init__(
        self,
        agent_type: AgentType,
        plugin_id: str,
        plugin_manager: PluginManager,
    ) -> None:
        self._agent_type = agent_type
        self._plugin_id = plugin_id
        self._plugin_manager = plugin_manager

    @property
    def agent_type(self) -> AgentType:
        return self._agent_type

    async def execute(self, subtask: SubTask) -> Any:
        input_data = subtask.input_data.copy()
        input_data["description"] = subtask.description

        result = await self._plugin_manager.execute(
            plugin_id=self._plugin_id,
            input_data=input_data,
        )

        if not result.success:
            raise RuntimeError(
                f"Plugin '{self._plugin_id}' execution failed: {result.errors}"
            )

        return result.output


def build_plugin_manager(loader: PluginLoader | None = None) -> PluginManager:
    """Build a PluginManager with in-memory registries."""
    from agent_reach.core.contracts.registry import InMemoryContractRegistry
    from agent_reach.core.plugin.static_loader import StaticPluginLoader
    from agent_reach.core.registry.registry import InMemoryRegistry

    if loader is None:
        loader = StaticPluginLoader()

    return PluginManager(
        loader=loader,
        registry=InMemoryRegistry(),
        contract_registry=InMemoryContractRegistry(),
    )
