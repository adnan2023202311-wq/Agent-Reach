"""
Tool Execution layer for Milestone 3.

Wraps the infrastructure ToolManager with:
- timeout handling
- exception isolation
- execution metrics

Layer: Application/Core — depends inward on infrastructure/ only.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from infrastructure.tool_manager import ToolManager


@dataclass
class ToolContext:
    """Context for a single tool invocation."""

    session_id: str = ""
    agent_type: str = ""
    tool_name: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 30.0


@dataclass
class ToolResult:
    """Outcome of a tool execution."""

    success: bool = False
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0


class ToolExecutor:
    """Executes tools with timeout, exception isolation, and metrics.

    Wraps ToolManager so that every tool call is sandboxed:
    - Timeouts are enforced via asyncio.wait_for
    - Exceptions are caught and converted to failed ToolResults
    - Duration is always recorded
    """

    def __init__(self, tool_manager: Optional[ToolManager] = None) -> None:
        self._tool_manager = tool_manager or ToolManager()

    @property
    def tool_manager(self) -> ToolManager:
        return self._tool_manager

    async def execute(self, context: ToolContext) -> ToolResult:
        """Execute a tool with isolation and timeout.

        Args:
            context: Tool execution context

        Returns:
            ToolResult with output or error
        """
        start = time.perf_counter()

        if not context.tool_name:
            return ToolResult(
                success=False,
                error="tool_name is required",
                duration_ms=self._elapsed_ms(start),
            )

        try:
            output = await asyncio.wait_for(
                self._tool_manager.call(
                    context.tool_name,
                    context.agent_type,
                    **context.parameters,
                ),
                timeout=context.timeout_seconds,
            )
            return ToolResult(
                success=True,
                output=output,
                duration_ms=self._elapsed_ms(start),
            )
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                error=f"Tool '{context.tool_name}' timed out after {context.timeout_seconds}s",
                duration_ms=self._elapsed_ms(start),
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Tool '{context.tool_name}' failed: {exc}",
                duration_ms=self._elapsed_ms(start),
            )

    def register_tool(
        self,
        name: str,
        func: Any,
        allowed_agents: Optional[frozenset[str]] = None,
    ) -> None:
        """Register a tool with the underlying ToolManager."""
        self._tool_manager.register(name, func, allowed_agents)

    @staticmethod
    def _elapsed_ms(start: float) -> float:
        return (time.perf_counter() - start) * 1000
