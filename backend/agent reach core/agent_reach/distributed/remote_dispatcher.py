"""
Distributed layer: Remote Dispatcher (M10.1 — Distributed Agent Cloud).

Layer: Application/Core — depends inward on domain/ only (for SubTask,
AgentResult, TaskStatus).

Routes subtasks to remote cluster nodes when the local node is
overloaded or lacks a required capability. Falls back to the local
AgentDispatcher transparently when no suitable remote node is available.

This is the "agent migration" surface: a subtask that can't run locally
is serialized and sent to a remote node's /api/v1/distributed/execute
endpoint. The remote node runs it through its own IntelligentPipeline
and returns the result.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from domain.exceptions import AgentExecutionError
from domain.models import AgentResult, AgentType, TaskStatus

logger = logging.getLogger(__name__)


class RemoteDispatcher:
    """Dispatches subtasks to remote cluster nodes with failover.

    Wraps the local AgentDispatcher. When the local node is at capacity
    or lacks a capability, the subtask is forwarded to a remote node.
    If the remote call fails, the subtask falls back to local execution
    (or fails if local can't handle it either).

    Parameters
    ----------
    local_dispatcher:
        The local AgentDispatcher to fall back to.
    node_registry:
        The NodeRegistry to query for available remote nodes.
    http_client:
        Optional async HTTP client for remote calls. If None, remote
        dispatch is disabled and all subtasks run locally.
    """

    def __init__(
        self,
        local_dispatcher: Any,
        node_registry: Any,
        http_client: Any = None,
    ) -> None:
        self._local = local_dispatcher
        self._registry = node_registry
        self._http = http_client
        self._remote_calls = 0
        self._remote_failures = 0
        self._local_fallbacks = 0

    async def dispatch(self, subtask: Any) -> AgentResult:
        """Execute a subtask locally or remotely with failover.

        Decision tree:
        1. If a remote node with the right capability is available AND
           we have an HTTP client, try remote dispatch.
        2. If remote dispatch fails (network, timeout, remote error),
           fall back to local dispatch.
        3. If no remote node is available, dispatch locally.
        """
        capability = subtask.agent_type.value

        # Try remote dispatch first if enabled and a node is available.
        if self._http is not None:
            node = self._registry.select_node(capability=capability)
            # Only use remote if it's NOT the local node.
            if node is not None and node.node_id != self._registry.local_node_id:
                try:
                    result = await self._dispatch_remote(subtask, node)
                    self._remote_calls += 1
                    return result
                except Exception as exc:
                    self._remote_failures += 1
                    logger.warning(
                        "RemoteDispatcher: remote dispatch to %s failed: %s — falling back to local",
                        node.node_id, exc,
                    )
                    # Mark the node as degraded so we don't keep retrying it.
                    node.status = "degraded" if hasattr(node, "status") else node.status

        # Fall back to local dispatch.
        self._local_fallbacks += 1
        return await self._local.dispatch(subtask)

    async def _dispatch_remote(self, subtask: Any, node: Any) -> AgentResult:
        """Serialize the subtask, send it to a remote node, deserialize the result."""
        start = time.perf_counter()
        payload = {
            "subtask_id": subtask.id,
            "agent_type": subtask.agent_type.value,
            "description": subtask.description,
            "input_data": subtask.input_data,
            "depends_on": list(subtask.depends_on),
        }
        endpoint = node.endpoint.rstrip("/")
        url = f"{endpoint}/api/v1/distributed/execute"

        # The http_client is expected to have an async post() method
        # that returns a dict with at least {"status": ..., "output": ...}.
        response = await self._http.post(url, json=payload)

        duration_ms = (time.perf_counter() - start) * 1000
        status_str = response.get("status", "failed")
        if status_str == "succeeded":
            return AgentResult(
                subtask_id=subtask.id,
                agent_type=subtask.agent_type,
                status=TaskStatus.SUCCEEDED,
                attempts=1,
                output=response.get("output"),
                duration_ms=duration_ms,
            )
        # Remote failure — raise so the caller falls back to local.
        raise AgentExecutionError(
            subtask.agent_type.value,
            subtask.id,
            Exception(response.get("error", "Remote execution failed")),
        )

    def stats(self) -> dict[str, Any]:
        return {
            "remote_calls": self._remote_calls,
            "remote_failures": self._remote_failures,
            "local_fallbacks": self._local_fallbacks,
        }
