"""
Distributed layer: Node Registry (M10.1 — Distributed Agent Cloud).

Layer: Application/Core — depends inward on domain/ only.

Tracks all execution nodes in the cluster: the local node plus any
remote nodes that have registered via the /api/v1/distributed/nodes
endpoint. Each node reports its capabilities, load, and health.

The registry is intentionally in-memory (single-process). For a true
multi-node deployment, swap this implementation for one backed by Redis
or etcd — the interface stays the same. This mirrors the same
"interface-first, one-impl-now" pattern used by the M9
ProviderConfigStore.
"""

from __future__ import annotations

import logging
import socket
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Optional

logger = logging.getLogger(__name__)


class NodeStatus(str, Enum):
    """Lifecycle state of a cluster node."""

    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    DRAINING = "draining"


@dataclass
class NodeInfo:
    """One execution node in the distributed cluster.

    A node is any process that can execute agents — the local backend
    process, a remote worker, or a future cloud executor. The registry
    uses this to route subtasks to the least-loaded capable node.
    """

    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    hostname: str = field(default_factory=socket.gethostname)
    endpoint: str = ""  # e.g. "http://10.0.0.5:8000"
    status: NodeStatus = NodeStatus.ONLINE
    capabilities: list[str] = field(default_factory=list)  # agent types this node can run
    max_concurrent: int = 4
    current_load: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    registered_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)

    def is_available(self) -> bool:
        """True if this node can accept new work."""
        return self.status == NodeStatus.ONLINE and self.current_load < self.max_concurrent

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "endpoint": self.endpoint,
            "status": self.status.value,
            "capabilities": list(self.capabilities),
            "max_concurrent": self.max_concurrent,
            "current_load": self.current_load,
            "metadata": dict(self.metadata),
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat,
        }


class NodeRegistry:
    """In-memory registry of all cluster nodes.

    Thread-safe. The local node is always present (registered at
    construction). Remote nodes register/deregister via the API.
    """

    HEARTBEAT_TIMEOUT_SECONDS = 60.0

    def __init__(self) -> None:
        self._lock = Lock()
        self._nodes: dict[str, NodeInfo] = {}
        # Register the local node immediately.
        local = NodeInfo(
            endpoint="local",
            capabilities=["research", "coding", "browser", "news", "writing",
                          "image", "planning", "memory", "social_media"],
            metadata={"role": "coordinator"},
        )
        self._nodes[local.node_id] = local
        self._local_node_id = local.node_id
        logger.info("NodeRegistry: local node registered as %s", local.node_id)

    @property
    def local_node_id(self) -> str:
        return self._local_node_id

    def register(self, node: NodeInfo) -> str:
        """Add a remote node to the cluster. Returns its node_id."""
        with self._lock:
            self._nodes[node.node_id] = node
            logger.info("NodeRegistry: registered node %s (%s)", node.node_id, node.endpoint)
            return node.node_id

    def deregister(self, node_id: str) -> bool:
        """Remove a node from the cluster. Returns True if it existed."""
        with self._lock:
            if node_id == self._local_node_id:
                logger.warning("NodeRegistry: refusing to deregister local node %s", node_id)
                return False
            existed = self._nodes.pop(node_id, None) is not None
            if existed:
                logger.info("NodeRegistry: deregistered node %s", node_id)
            return existed

    def heartbeat(self, node_id: str, load: Optional[int] = None) -> bool:
        """Update a node's last-seen timestamp. Returns False if unknown."""
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return False
            node.last_heartbeat = time.time()
            if load is not None:
                node.current_load = load
            return True

    def get(self, node_id: str) -> Optional[NodeInfo]:
        with self._lock:
            return self._nodes.get(node_id)

    def list_nodes(self, status: Optional[NodeStatus] = None) -> list[NodeInfo]:
        with self._lock:
            nodes = list(self._nodes.values())
        if status is not None:
            nodes = [n for n in nodes if n.status == status]
        return nodes

    def list_available(self, capability: Optional[str] = None) -> list[NodeInfo]:
        """Return nodes that can accept work, optionally filtered by capability.

        Sorted by current load (least-loaded first) for round-robin-ish
        scheduling without the overhead of a separate scheduler.
        """
        with self._lock:
            nodes = list(self._nodes.values())
        available = [n for n in nodes if n.is_available()]
        if capability:
            available = [n for n in available if capability in n.capabilities]
        available.sort(key=lambda n: n.current_load)
        return available

    def select_node(self, capability: Optional[str] = None) -> Optional[NodeInfo]:
        """Pick the best node for a subtask. Returns None if none available."""
        nodes = self.list_available(capability)
        return nodes[0] if nodes else None

    def update_load(self, node_id: str, delta: int) -> None:
        """Increment or decrement a node's current load."""
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return
            node.current_load = max(0, node.current_load + delta)

    def mark_stale_offline(self) -> int:
        """Mark nodes whose heartbeats expired as OFFLINE. Returns count."""
        now = time.time()
        count = 0
        with self._lock:
            for node in self._nodes.values():
                if node.node_id == self._local_node_id:
                    continue
                if node.status == NodeStatus.ONLINE and (now - node.last_heartbeat) > self.HEARTBEAT_TIMEOUT_SECONDS:
                    node.status = NodeStatus.OFFLINE
                    count += 1
                    logger.warning(
                        "NodeRegistry: node %s marked OFFLINE (heartbeat expired)",
                        node.node_id,
                    )
        return count

    def cluster_stats(self) -> dict[str, Any]:
        """Aggregate cluster health for the monitoring center."""
        with self._lock:
            nodes = list(self._nodes.values())
        total = len(nodes)
        online = sum(1 for n in nodes if n.status == NodeStatus.ONLINE)
        offline = sum(1 for n in nodes if n.status == NodeStatus.OFFLINE)
        degraded = sum(1 for n in nodes if n.status == NodeStatus.DEGRADED)
        draining = sum(1 for n in nodes if n.status == NodeStatus.DRAINING)
        total_capacity = sum(n.max_concurrent for n in nodes if n.is_available())
        total_load = sum(n.current_load for n in nodes)
        return {
            "total_nodes": total,
            "online": online,
            "offline": offline,
            "degraded": degraded,
            "draining": draining,
            "total_capacity": total_capacity,
            "total_load": total_load,
            "utilization": total_load / max(1, total_capacity),
        }


# ── Module-level singleton ──────────────────────────────────────────────
_registry: Optional[NodeRegistry] = None


def get_node_registry() -> NodeRegistry:
    """Return the process-wide NodeRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = NodeRegistry()
    return _registry
