"""
Tests for ToolExecutor, ToolContext, and ToolResult.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from core.tool_executor import ToolContext, ToolExecutor, ToolResult


async def test_tool_result_defaults() -> None:
    """ToolResult defaults to failure with no output."""
    result = ToolResult()
    assert result.success is False
    assert result.output is None
    assert result.error is None
    assert result.duration_ms == 0.0


async def test_tool_context_defaults() -> None:
    """ToolContext has sensible defaults."""
    ctx = ToolContext()
    assert ctx.timeout_seconds == 30.0
    assert ctx.parameters == {}


async def test_execute_success() -> None:
    """ToolExecutor returns success for a working tool."""
    executor = ToolExecutor()

    async def echo_tool(**kwargs: Any) -> str:
        return f"echo: {kwargs.get('msg', '')}"

    executor.register_tool("echo", echo_tool)

    result = await executor.execute(
        ToolContext(tool_name="echo", agent_type="research", parameters={"msg": "hi"})
    )
    assert result.success is True
    assert result.output == "echo: hi"
    assert result.duration_ms >= 0


async def test_execute_missing_tool_name() -> None:
    """Executing with no tool_name returns an error."""
    executor = ToolExecutor()
    result = await executor.execute(ToolContext())
    assert result.success is False
    assert "tool_name is required" in result.error


async def test_execute_unregistered_tool() -> None:
    """Executing an unregistered tool returns an error."""
    executor = ToolExecutor()
    result = await executor.execute(
        ToolContext(tool_name="missing", agent_type="research")
    )
    assert result.success is False
    assert "missing" in result.error


async def test_execute_timeout() -> None:
    """A slow tool is timed out."""
    executor = ToolExecutor()

    async def slow_tool(**kwargs: Any) -> str:
        await asyncio.sleep(10)
        return "too late"

    executor.register_tool("slow", slow_tool)

    result = await executor.execute(
        ToolContext(tool_name="slow", agent_type="research", timeout_seconds=0.05)
    )
    assert result.success is False
    assert "timed out" in result.error


async def test_execute_exception_isolation() -> None:
    """A crashing tool does not propagate the exception."""
    executor = ToolExecutor()

    async def bad_tool(**kwargs: Any) -> str:
        raise RuntimeError("boom")

    executor.register_tool("bad", bad_tool)

    result = await executor.execute(
        ToolContext(tool_name="bad", agent_type="research")
    )
    assert result.success is False
    assert "boom" in result.error


async def test_execute_permission_denied() -> None:
    """A tool restricted to other agents returns permission error."""
    executor = ToolExecutor()

    async def admin_tool(**kwargs: Any) -> str:
        return "secret"

    executor.register_tool("admin", admin_tool, allowed_agents=frozenset({"admin"}))

    result = await executor.execute(
        ToolContext(tool_name="admin", agent_type="research")
    )
    assert result.success is False
    assert "not permitted" in result.error


async def test_tool_manager_property() -> None:
    """ToolExecutor exposes its underlying ToolManager."""
    executor = ToolExecutor()
    assert executor.tool_manager is not None
