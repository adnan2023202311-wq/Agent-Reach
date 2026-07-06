"""
Tests for AgentBase.

Covers lifecycle hooks, validation, and execution flow.
"""

from __future__ import annotations

from typing import Any

import pytest

from agents.base import AgentBase
from domain.models import AgentType, SubTask


class FakeAgent(AgentBase):
    """Concrete agent for testing AgentBase mechanics."""

    def __init__(self) -> None:
        super().__init__()
        self.init_calls = 0
        self.shutdown_calls = 0
        self.execute_calls = 0

    @property
    def agent_type(self) -> AgentType:
        return AgentType.RESEARCH

    async def _initialize_impl(self) -> None:
        self.init_calls += 1

    async def _shutdown_impl(self) -> None:
        self.shutdown_calls += 1

    async def _execute_impl(self, subtask: SubTask) -> Any:
        self.execute_calls += 1
        return {"echo": subtask.description}


class ValidatingAgent(AgentBase):
    """Agent with custom validation."""

    @property
    def agent_type(self) -> AgentType:
        return AgentType.CODING

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        if "required" not in input_data:
            return ["Missing 'required' field"]
        return []

    def validate_output(self, output: Any) -> list[str]:
        if not isinstance(output, dict) or "result" not in output:
            return ["Output must contain 'result'"]
        return []

    async def _execute_impl(self, subtask: SubTask) -> Any:
        return subtask.input_data


async def test_initialize_called_once() -> None:
    """initialize() is idempotent."""
    agent = FakeAgent()
    await agent.initialize()
    await agent.initialize()
    assert agent.init_calls == 1
    assert agent.is_initialized


async def test_shutdown_called_once() -> None:
    """shutdown() is idempotent."""
    agent = FakeAgent()
    await agent.initialize()
    await agent.shutdown()
    await agent.shutdown()
    assert agent.shutdown_calls == 1
    assert not agent.is_initialized


async def test_execute_calls_initialize_and_impl() -> None:
    """execute() initializes then runs _execute_impl."""
    agent = FakeAgent()
    subtask = SubTask(agent_type=AgentType.RESEARCH, description="test")
    result = await agent.execute(subtask)
    assert agent.init_calls == 1
    assert agent.execute_calls == 1
    assert result == {"echo": "test"}


async def test_input_validation_failure() -> None:
    """Invalid input raises before _execute_impl."""
    agent = ValidatingAgent()
    subtask = SubTask(agent_type=AgentType.CODING, description="test", input_data={})
    with pytest.raises(ValueError) as exc_info:
        await agent.execute(subtask)
    assert "Input validation failed" in str(exc_info.value)


async def test_output_validation_failure() -> None:
    """Invalid output raises after _execute_impl."""
    agent = ValidatingAgent()
    subtask = SubTask(
        agent_type=AgentType.CODING,
        description="test",
        input_data={"required": True},
    )
    with pytest.raises(ValueError) as exc_info:
        await agent.execute(subtask)
    assert "Output validation failed" in str(exc_info.value)


async def test_valid_input_output_passes() -> None:
    """Valid input and output allow execution to complete."""
    agent = ValidatingAgent()
    subtask = SubTask(
        agent_type=AgentType.CODING,
        description="test",
        input_data={"required": True, "result": 42},
    )
    result = await agent.execute(subtask)
    assert result == {"required": True, "result": 42}


async def test_agent_type_property() -> None:
    """agent_type is exposed as a property."""
    agent = FakeAgent()
    assert agent.agent_type == AgentType.RESEARCH
