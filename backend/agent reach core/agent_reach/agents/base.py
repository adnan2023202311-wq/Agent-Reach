"""
Agents layer: AgentBase.

Layer: Adapters — implements domain.interfaces.Agent.

Abstract base class for all runtime-aware agents.
Provides lifecycle hooks (initialize, execute, shutdown),
input/output validation, and runtime integration.

Existing agents (ResearchAgent, CodingAgent, PluginAgent) are NOT
required to inherit from this class — they continue to work through
the domain.interfaces.Agent abstraction. New agents should inherit
from AgentBase to gain runtime capabilities.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from domain.interfaces import Agent
from domain.models import AgentType, SubTask


class AgentBase(Agent):
    """
    Abstract base for runtime-aware agents.

    Subclasses must implement:
    - agent_type (property)
    - _execute_impl (async method)

    Optional hooks:
    - initialize
    - shutdown
    - validate_input
    - validate_output
    """

    def __init__(self) -> None:
        self._initialized = False

    @property
    @abstractmethod
    def agent_type(self) -> AgentType:
        """Which AgentType this instance handles."""

    async def initialize(self) -> None:
        """Lifecycle hook called before the agent is used.

        Idempotent — safe to call multiple times.
        """
        if not self._initialized:
            await self._initialize_impl()
            self._initialized = True

    async def shutdown(self) -> None:
        """Lifecycle hook called when the agent is being retired.

        Idempotent — safe to call multiple times.
        """
        if self._initialized:
            await self._shutdown_impl()
            self._initialized = False

    async def execute(self, subtask: SubTask) -> Any:
        """Execute a subtask with validation and hooks.

        This is the public entrypoint; subclasses override
        _execute_impl for the actual work.
        """
        await self.initialize()

        input_errors = self.validate_input(subtask.input_data)
        if input_errors:
            raise ValueError(f"Input validation failed: {input_errors}")

        result = await self._execute_impl(subtask)

        output_errors = self.validate_output(result)
        if output_errors:
            raise ValueError(f"Output validation failed: {output_errors}")

        return result

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        """Validate input data before execution.

        Returns a list of error messages (empty if valid).
        Subclasses may override for custom validation.
        """
        return []

    def validate_output(self, output: Any) -> list[str]:
        """Validate output data after execution.

        Returns a list of error messages (empty if valid).
        Subclasses may override for custom validation.
        """
        return []

    @abstractmethod
    async def _execute_impl(self, subtask: SubTask) -> Any:
        """Concrete execution logic. Must be implemented by subclasses."""

    async def _initialize_impl(self) -> None:
        """Optional initialization logic. Override if needed."""

    async def _shutdown_impl(self) -> None:
        """Optional shutdown logic. Override if needed."""

    @property
    def is_initialized(self) -> bool:
        return self._initialized
