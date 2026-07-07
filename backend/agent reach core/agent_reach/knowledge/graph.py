"""
Knowledge Graph (M7.8).

Internal knowledge graph linking projects, files, agents, skills,
memory, workflows, prompts, and providers.

Nodes with types and edges with relationships.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class NodeType(str, Enum):
    PROJECT = "project"
    FILE = "file"
    AGENT = "agent"
    SKILL = "skill"
    MEMORY = "memory"
    WORKFLOW = "workflow"
    PROMPT = "prompt"
    PROVIDER = "provider"
    EXECUTION = "execution"


class EdgeType(str, Enum):
    DEPENDS_ON = "depends_on"
    GENERATED_BY = "generated_by"
    RELATED_TO = "related_to"
    LEARNED_FROM = "learned_from"
    USES = "uses"
    REQUIRES = "requires"
    SUPPORTS = "supports"
    PART_OF = "part_of"
    PRECEDES = "precedes"


@dataclass
class KnowledgeNode:
    """A node in the knowledge graph."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    node_type: NodeType = NodeType.PROJECT
    label: str = ""
    description: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.node_type.value,
            "label": self.label,
            "description": self.description,
            "properties": dict(self.properties),
        }


@dataclass
class KnowledgeEdge:
    """An edge connecting two knowledge nodes."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str = ""
    target_id: str = ""
    edge_type: EdgeType = EdgeType.RELATED_TO
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source_id,
            "target": self.target_id,
            "type": self.edge_type.value,
            "weight": self.weight,
        }


class KnowledgeGraph:
    """In-memory knowledge graph with typed nodes and edges.

    Connects all Agent-Reach entities: projects, agents, skills,
    memory, workflows, prompts, providers, and executions.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, KnowledgeNode] = {}
        self._edges: dict[str, KnowledgeEdge] = {}
        # Adjacency for efficient traversal
        self._outgoing: dict[str, list[str]] = defaultdict(list)
        self._incoming: dict[str, list[str]] = defaultdict(list)
        # Index by type
        self._by_type: dict[NodeType, list[str]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Node management
    # ------------------------------------------------------------------

    def add_node(
        self,
        node_type: NodeType,
        label: str,
        description: str = "",
        properties: Optional[dict[str, Any]] = None,
        node_id: str = "",
    ) -> str:
        """Add a node to the graph. Returns node ID."""
        node = KnowledgeNode(
            id=node_id or str(uuid.uuid4()),
            node_type=node_type,
            label=label,
            description=description,
            properties=dict(properties or {}),
        )
        self._nodes[node.id] = node
        self._by_type[node_type].append(node.id)
        return node.id

    def get_node(self, node_id: str) -> Optional[KnowledgeNode]:
        """Get a node by ID."""
        return self._nodes.get(node_id)

    def find_nodes(
        self,
        node_type: Optional[NodeType] = None,
        label_contains: str = "",
    ) -> list[KnowledgeNode]:
        """Find nodes by type and/or label search."""
        results: list[KnowledgeNode] = []
        candidates = (
            [self._nodes[nid] for nid in self._by_type.get(node_type, [])]
            if node_type
            else list(self._nodes.values())
        )
        for node in candidates:
            if label_contains and label_contains.lower() not in node.label.lower():
                continue
            results.append(node)
        return results

    def remove_node(self, node_id: str) -> bool:
        """Remove a node and all its edges."""
        if node_id not in self._nodes:
            return False
        del self._nodes[node_id]

        # Remove edges
        for edge_id in list(self._outgoing.get(node_id, [])):
            edge = self._edges.get(edge_id)
            if edge:
                self._incoming[edge.target_id].remove(edge_id)
            self._edges.pop(edge_id, None)
        self._outgoing.pop(node_id, None)

        for edge_id in list(self._incoming.get(node_id, [])):
            edge = self._edges.get(edge_id)
            if edge:
                self._outgoing[edge.source_id].remove(edge_id)
            self._edges.pop(edge_id, None)
        self._incoming.pop(node_id, None)

        # Remove from type index
        for ntype, nids in self._by_type.items():
            if node_id in nids:
                nids.remove(node_id)

        return True

    # ------------------------------------------------------------------
    # Edge management
    # ------------------------------------------------------------------

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType = EdgeType.RELATED_TO,
        weight: float = 1.0,
        properties: Optional[dict[str, Any]] = None,
    ) -> Optional[str]:
        """Add an edge between two nodes. Returns edge ID or None."""
        if source_id not in self._nodes or target_id not in self._nodes:
            return None

        edge = KnowledgeEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=weight,
            properties=dict(properties or {}),
        )
        self._edges[edge.id] = edge
        self._outgoing[source_id].append(edge.id)
        self._incoming[target_id].append(edge.id)
        return edge.id

    def get_edge(self, edge_id: str) -> Optional[KnowledgeEdge]:
        """Get an edge by ID."""
        return self._edges.get(edge_id)

    def remove_edge(self, edge_id: str) -> bool:
        """Remove an edge."""
        edge = self._edges.pop(edge_id, None)
        if edge is None:
            return False
        if edge_id in self._outgoing.get(edge.source_id, []):
            self._outgoing[edge.source_id].remove(edge_id)
        if edge_id in self._incoming.get(edge.target_id, []):
            self._incoming[edge.target_id].remove(edge_id)
        return True

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    def get_neighbors(
        self,
        node_id: str,
        direction: str = "both",
        edge_type: Optional[EdgeType] = None,
    ) -> list[tuple[KnowledgeNode, KnowledgeEdge, str]]:
        """Get neighbors of a node.

        Args:
            node_id: The node to get neighbors of.
            direction: "outgoing", "incoming", or "both".
            edge_type: Filter by edge type.

        Returns:
            List of (node, edge, direction) tuples.
        """
        results: list[tuple[KnowledgeNode, KnowledgeEdge, str]] = []

        if direction in ("outgoing", "both"):
            for edge_id in self._outgoing.get(node_id, []):
                edge = self._edges.get(edge_id)
                if edge is None:
                    continue
                if edge_type and edge.edge_type != edge_type:
                    continue
                node = self._nodes.get(edge.target_id)
                if node:
                    results.append((node, edge, "outgoing"))

        if direction in ("incoming", "both"):
            for edge_id in self._incoming.get(node_id, []):
                edge = self._edges.get(edge_id)
                if edge is None:
                    continue
                if edge_type and edge.edge_type != edge_type:
                    continue
                node = self._nodes.get(edge.source_id)
                if node:
                    results.append((node, edge, "incoming"))

        return results

    def traverse(
        self,
        start_id: str,
        max_depth: int = 3,
        edge_type: Optional[EdgeType] = None,
    ) -> list[tuple[KnowledgeNode, int]]:
        """BFS traversal from a start node.

        Returns list of (node, depth) tuples.
        """
        visited: set[str] = {start_id}
        results: list[tuple[KnowledgeNode, int]] = []
        frontier = [(start_id, 0)]

        while frontier:
            current_id, depth = frontier.pop(0)
            if depth >= max_depth:
                continue

            for edge_id in self._outgoing.get(current_id, []):
                edge = self._edges.get(edge_id)
                if edge is None:
                    continue
                if edge_type and edge.edge_type != edge_type:
                    continue
                target = edge.target_id
                if target in visited:
                    continue
                visited.add(target)
                node = self._nodes.get(target)
                if node:
                    results.append((node, depth + 1))
                    frontier.append((target, depth + 1))

        return results

    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
    ) -> Optional[list[str]]:
        """Find the shortest path between two nodes (BFS)."""
        if source_id not in self._nodes or target_id not in self._nodes:
            return None
        if source_id == target_id:
            return [source_id]

        visited = {source_id}
        parent: dict[str, str] = {}
        queue = [source_id]

        while queue:
            current = queue.pop(0)
            for edge_id in self._outgoing.get(current, []):
                edge = self._edges.get(edge_id)
                if edge is None:
                    continue
                neighbor = edge.target_id
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                parent[neighbor] = current
                if neighbor == target_id:
                    # Reconstruct path
                    path = [target_id]
                    while path[-1] != source_id:
                        path.append(parent[path[-1]])
                    path.reverse()
                    if len(path) - 1 <= max_depth:
                        return path
                    return None
                queue.append(neighbor)

        return None

    # ------------------------------------------------------------------
    # Subgraphs
    # ------------------------------------------------------------------

    def get_subgraph(
        self,
        node_ids: list[str],
        include_edges: bool = True,
    ) -> dict[str, Any]:
        """Extract a subgraph containing specified nodes."""
        nodes = {nid: self._nodes[nid] for nid in node_ids if nid in self._nodes}
        edges: list[KnowledgeEdge] = []
        if include_edges:
            for edge in self._edges.values():
                if edge.source_id in nodes and edge.target_id in nodes:
                    edges.append(edge)

        return {
            "nodes": [n.to_dict() for n in nodes.values()],
            "edges": [e.to_dict() for e in edges],
        }

    def get_by_type(self, node_type: NodeType) -> list[KnowledgeNode]:
        """Get all nodes of a specific type."""
        return [self._nodes[nid] for nid in self._by_type.get(node_type, [])]

    def get_related_by_type(
        self,
        node_id: str,
        target_type: NodeType,
        edge_type: Optional[EdgeType] = None,
        max_depth: int = 2,
    ) -> list[KnowledgeNode]:
        """Find nodes of a specific type related to a given node."""
        traversed = self.traverse(node_id, max_depth=max_depth, edge_type=edge_type)
        return [n for n, _ in traversed if n.node_type == target_type]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get knowledge graph statistics."""
        type_counts = {
            nt.value: len(ids) for nt, ids in self._by_type.items()
        }
        edge_type_counts: dict[str, int] = defaultdict(int)
        for edge in self._edges.values():
            edge_type_counts[edge.edge_type.value] += 1

        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "node_types": type_counts,
            "edge_types": dict(edge_type_counts),
            "density": (
                len(self._edges) / max(1, len(self._nodes) * (len(self._nodes) - 1))
            ),
        }

    def clear(self) -> None:
        """Remove all nodes and edges."""
        self._nodes.clear()
        self._edges.clear()
        self._outgoing.clear()
        self._incoming.clear()
        self._by_type.clear()
