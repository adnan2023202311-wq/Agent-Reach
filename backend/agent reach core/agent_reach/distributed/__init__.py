"""
Distributed layer (M10.1 + M10.2).

Package for distributed execution, cluster management, and agent swarm
intelligence. Depends inward on domain/ only.
"""

from distributed.node_registry import NodeRegistry, NodeInfo, NodeStatus, get_node_registry
from distributed.remote_dispatcher import RemoteDispatcher
from distributed.swarm import (
    AgentSwarm,
    SwarmOrchestrator,
    SwarmRole,
    SwarmResult,
    default_scorer,
)

__all__ = [
    "NodeRegistry",
    "NodeInfo",
    "NodeStatus",
    "get_node_registry",
    "RemoteDispatcher",
    "AgentSwarm",
    "SwarmOrchestrator",
    "SwarmRole",
    "SwarmResult",
    "default_scorer",
]
