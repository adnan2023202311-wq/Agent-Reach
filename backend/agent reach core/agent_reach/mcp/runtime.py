"""
MCP Runtime: native Model Context Protocol implementation.

Inspired by the MCP standard tool protocol, but built natively
without vendor-specific integrations or external SDK dependencies.

Provides:
- MCPToolDefinition: schema for a tool callable via MCP
- MCPRequest: standardized execution request
- MCPResponse: standardized execution response
- MCPRuntime: in-process registry and executor for MCP tools

Layer: Application/Core — depends inward on domain/ and infrastructure/ only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


@dataclass
class MCPToolDefinition:
    """Schema definition for an MCP-exposed tool."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    required_parameters: list[str] = field(default_factory=list)


@dataclass
class MCPRequest:
    """Standardized request to invoke an MCP tool."""

    tool_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPResponse:
    """Standardized response from an MCP tool invocation."""

    request_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0


class MCPRuntime:
    """In-process MCP runtime for tool registration and execution.

    Tools are registered with a schema definition and an executor.
    Requests are validated against the schema before execution.
    """

    def __init__(self) -> None:
        self._tools: dict[str, MCPToolDefinition] = {}
        self._executors: dict[str, Callable[[MCPRequest], Awaitable[Any]]] = {}

    def register_tool(
        self,
        definition: MCPToolDefinition,
        executor: Callable[[MCPRequest], Awaitable[Any]],
    ) -> None:
        """Register a tool with the MCP runtime."""
        self._tools[definition.name] = definition
        self._executors[definition.name] = executor

    def unregister_tool(self, name: str) -> bool:
        """Remove a tool registration."""
        if name not in self._tools:
            return False
        del self._tools[name]
        del self._executors[name]
        return True

    def list_tools(self) -> list[MCPToolDefinition]:
        """List all registered tool definitions."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> Optional[MCPToolDefinition]:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def _validate_request(self, request: MCPRequest) -> Optional[str]:
        """Validate a request against the tool schema.

        Returns an error message if invalid, None if valid.
        """
        definition = self._tools.get(request.tool_name)
        if definition is None:
            return f"Tool '{request.tool_name}' is not registered"

        for param in definition.required_parameters:
            if param not in request.parameters:
                return f"Missing required parameter '{param}' for tool '{request.tool_name}'"

        return None

    async def execute(self, request: MCPRequest) -> MCPResponse:
        """Execute an MCP request.

        Validates the request, invokes the executor, and returns a
        standardized response.
        """
        start = time.perf_counter()
        request_id = request.request_id or str(int(time.time() * 1000))

        error = self._validate_request(request)
        if error is not None:
            return MCPResponse(
                request_id=request_id,
                success=False,
                error=error,
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        executor = self._executors[request.tool_name]
        try:
            result = await executor(request)
            return MCPResponse(
                request_id=request_id,
                success=True,
                result=result,
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as exc:
            return MCPResponse(
                request_id=request_id,
                success=False,
                error=f"Execution failed: {exc}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

    def clear(self) -> None:
        """Remove all tool registrations. Useful for testing."""
        self._tools.clear()
        self._executors.clear()
