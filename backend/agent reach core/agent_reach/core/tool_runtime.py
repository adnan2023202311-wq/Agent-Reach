"""
Live Tool Runtime (M9.6).

Layer: Application/Core — composes the existing infrastructure pieces:
ToolRegistry (metadata, permissions, enable/disable) and the same
timeout/isolation discipline as core/tool_executor.py. It does NOT
replace either — it adds the execution-history and metrics surface
Milestone 9.6 requires ("Display execution history, failures, retries
and metrics") on top of them.

Every execution is recorded in a bounded history buffer with duration,
outcome, attempt count, and error detail, so the Tools screen becomes
a live window into real tool activity.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

from infrastructure.tool_registry import ToolRegistry


@dataclass
class ToolExecution:
    """One recorded tool execution."""

    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str = ""
    agent_type: str = ""
    started_at: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    success: bool = False
    attempts: int = 1
    error: Optional[str] = None
    output_preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "tool_name": self.tool_name,
            "agent_type": self.agent_type,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "attempts": self.attempts,
            "error": self.error,
            "output_preview": self.output_preview,
        }


class ToolRuntime:
    """Executes registered tools with isolation, retries, and history.

    Parameters
    ----------
    registry:
        The shared ToolRegistry (injected — composition.py owns it).
    max_history:
        Bound on the execution history buffer.
    default_timeout_seconds:
        Per-call timeout enforced with asyncio.wait_for.
    max_retries:
        How many additional attempts a failed call gets. Retries are
        recorded honestly in the execution record.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        max_history: int = 1000,
        default_timeout_seconds: float = 30.0,
        max_retries: int = 1,
    ) -> None:
        if max_history < 1:
            raise ValueError("max_history must be >= 1")
        self._registry = registry
        self._history: deque[ToolExecution] = deque(maxlen=max_history)
        self._default_timeout = default_timeout_seconds
        self._max_retries = max(0, max_retries)

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    # ── Execution ───────────────────────────────────────────────

    async def execute(
        self,
        tool_name: str,
        agent_type: str = "api",
        parameters: Optional[dict[str, Any]] = None,
        timeout_seconds: Optional[float] = None,
    ) -> ToolExecution:
        """Execute a tool and record the outcome in history.

        Never raises for tool failures — errors are captured on the
        returned ToolExecution so callers (and the UI) always get a
        record. Unknown/disabled tools also produce failed records.
        """
        parameters = parameters or {}
        timeout = timeout_seconds or self._default_timeout
        record = ToolExecution(tool_name=tool_name, agent_type=agent_type)
        start = time.perf_counter()

        attempts = 0
        last_error: Optional[str] = None
        output: Any = None
        succeeded = False

        while attempts <= self._max_retries:
            attempts += 1
            try:
                output = await asyncio.wait_for(
                    self._registry.call(tool_name, agent_type, **parameters),
                    timeout=timeout,
                )
                succeeded = True
                break
            except asyncio.TimeoutError:
                last_error = f"Tool '{tool_name}' timed out after {timeout}s"
            except (KeyError, PermissionError) as exc:
                # Not-registered / disabled / permission-denied are not
                # transient — retrying cannot help.
                last_error = str(exc)
                break
            except Exception as exc:  # noqa: BLE001 — isolation boundary
                last_error = f"{type(exc).__name__}: {exc}"

        record.duration_ms = (time.perf_counter() - start) * 1000
        record.attempts = attempts
        record.success = succeeded
        record.error = None if succeeded else last_error
        if succeeded:
            record.output_preview = str(output)[:500]
        self._history.append(record)
        return record

    # ── History & metrics ───────────────────────────────────────

    def get_history(
        self,
        tool_name: str = "",
        limit: int = 50,
        failures_only: bool = False,
    ) -> list[ToolExecution]:
        """Recent executions, newest first, optionally filtered."""
        records = list(self._history)
        if tool_name:
            records = [r for r in records if r.tool_name == tool_name]
        if failures_only:
            records = [r for r in records if not r.success]
        return list(reversed(records))[: max(0, limit)]

    def get_metrics(self, tool_name: str = "") -> dict[str, Any]:
        """Aggregate execution metrics, overall or per tool."""
        records = [
            r for r in self._history if not tool_name or r.tool_name == tool_name
        ]
        total = len(records)
        if total == 0:
            return {
                "total_executions": 0,
                "successes": 0,
                "failures": 0,
                "success_rate": 0.0,
                "retries": 0,
                "avg_duration_ms": 0.0,
                "max_duration_ms": 0.0,
            }
        successes = sum(1 for r in records if r.success)
        durations = [r.duration_ms for r in records]
        return {
            "total_executions": total,
            "successes": successes,
            "failures": total - successes,
            "success_rate": successes / total,
            "retries": sum(r.attempts - 1 for r in records),
            "avg_duration_ms": sum(durations) / total,
            "max_duration_ms": max(durations),
        }

    def get_per_tool_metrics(self) -> dict[str, dict[str, Any]]:
        """Metrics broken down by tool name."""
        names = {r.tool_name for r in self._history}
        return {name: self.get_metrics(name) for name in sorted(names)}

    def clear_history(self) -> None:
        """Remove all execution records. Useful for testing."""
        self._history.clear()
