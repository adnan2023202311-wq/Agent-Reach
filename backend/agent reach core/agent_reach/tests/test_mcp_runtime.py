"""Tests for MCP Runtime (M4.4)."""

from __future__ import annotations

import pytest

from mcp.runtime import MCPRequest, MCPRuntime, MCPToolDefinition


async def _add_tool(request: MCPRequest) -> int:
    a = request.parameters.get("a", 0)
    b = request.parameters.get("b", 0)
    return a + b


async def _failing_tool(request: MCPRequest) -> None:
    raise RuntimeError("intentional failure")


class TestMCPRuntime:
    def test_register_and_list(self) -> None:
        runtime = MCPRuntime()
        definition = MCPToolDefinition(name="add", description="Add two numbers")
        runtime.register_tool(definition, _add_tool)
        tools = runtime.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "add"

    def test_has_tool(self) -> None:
        runtime = MCPRuntime()
        runtime.register_tool(MCPToolDefinition(name="x"), _add_tool)
        assert runtime.has_tool("x") is True
        assert runtime.has_tool("y") is False

    def test_get_tool(self) -> None:
        runtime = MCPRuntime()
        runtime.register_tool(MCPToolDefinition(name="x", description="desc"), _add_tool)
        tool = runtime.get_tool("x")
        assert tool is not None
        assert tool.description == "desc"
        assert runtime.get_tool("missing") is None

    def test_unregister(self) -> None:
        runtime = MCPRuntime()
        runtime.register_tool(MCPToolDefinition(name="x"), _add_tool)
        assert runtime.unregister_tool("x") is True
        assert runtime.has_tool("x") is False
        assert runtime.unregister_tool("x") is False

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        runtime = MCPRuntime()
        runtime.register_tool(MCPToolDefinition(name="add"), _add_tool)
        request = MCPRequest(tool_name="add", parameters={"a": 2, "b": 3})
        response = await runtime.execute(request)
        assert response.success is True
        assert response.result == 5
        assert response.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_missing_tool(self) -> None:
        runtime = MCPRuntime()
        request = MCPRequest(tool_name="missing")
        response = await runtime.execute(request)
        assert response.success is False
        assert "not registered" in response.error

    @pytest.mark.asyncio
    async def test_execute_missing_required_param(self) -> None:
        runtime = MCPRuntime()
        definition = MCPToolDefinition(
            name="greet",
            required_parameters=["name"],
        )
        runtime.register_tool(definition, _add_tool)
        request = MCPRequest(tool_name="greet", parameters={})
        response = await runtime.execute(request)
        assert response.success is False
        assert "Missing required parameter" in response.error

    @pytest.mark.asyncio
    async def test_execute_exception_isolation(self) -> None:
        runtime = MCPRuntime()
        runtime.register_tool(MCPToolDefinition(name="fail"), _failing_tool)
        request = MCPRequest(tool_name="fail")
        response = await runtime.execute(request)
        assert response.success is False
        assert "intentional failure" in response.error

    def test_clear(self) -> None:
        runtime = MCPRuntime()
        runtime.register_tool(MCPToolDefinition(name="x"), _add_tool)
        runtime.clear()
        assert runtime.list_tools() == []
