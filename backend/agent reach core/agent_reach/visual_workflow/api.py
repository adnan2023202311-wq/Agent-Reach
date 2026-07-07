"""
Visual Workflow layer: Visual Workflow API (M6.8).

Layer: Application/Core — depends inward on workflows/ only.

Provides the backend API required for future visual workflow editing.
No frontend implementation is required.

Capabilities:
- **serialize workflow**: Workflow → JSON-compatible dict (reuses
  Workflow.to_dict)
- **deserialize workflow**: dict → Workflow (reuses Workflow.from_dict)
- **graph representation**: Workflow → nodes + edges for rendering
  in a visual editor
- **workflow validation**: structural + semantic validation (reuses
  WorkflowValidator)

The graph representation converts a Workflow into a node-edge graph
that a visual editor can render. Each step becomes a node; each
dependency (depends_on) becomes a directed edge. This is a read-only
view — the graph is derived from the Workflow, not stored separately.

Design notes
------------
- The graph is always derived from the current Workflow definition.
  There is no separate "graph state" to keep in sync.
- Node positions are not stored — the visual editor will handle
  layout. The graph only provides the topological structure.
- The API is a set of pure functions plus a thin ``VisualWorkflowAPI``
  class that bundles serialization, deserialization, graph
  and validation behind one interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from workflows.models import (
    StepType,
    Workflow,
    WorkflowStep,
)
from workflows.validation import ValidationResult, WorkflowValidator


# ---------------------------------------------------------------------------
# Graph models
# ---------------------------------------------------------------------------


@dataclass
class WorkflowNode:
    """A node in the visual workflow graph (one per step)."""

    step_id: str
    name: str
    type: str  # "agent" | "tool"
    target: str
    has_condition: bool = False
    inputs: dict[str, Any] = field(default_factory=dict)
    output_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "type": self.type,
            "target": self.target,
            "has_condition": self.has_condition,
            "inputs": dict(self.inputs),
            "output_keys": list(self.output_keys),
        }


@dataclass
class WorkflowEdge:
    """A directed edge in the visual workflow graph (dependency)."""

    source: str  # step_id
    target: str  # step_id
    label: str = ""  # optional label (e.g. "condition: true")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "source": self.source,
            "target": self.target,
            "label": self.label,
        }


@dataclass
class WorkflowGraph:
    """A node-edge graph representation of a Workflow.

    Attributes:
        workflow_id: the workflow this graph represents.
        nodes: list of WorkflowNode (one per step).
        edges: list of WorkflowEdge (one per dependency).
    """

    workflow_id: str
    nodes: list[WorkflowNode] = field(default_factory=list)
    edges: list[WorkflowEdge] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "workflow_id": self.workflow_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    def get_node(self, step_id: str) -> Optional[WorkflowNode]:
        """Return the node for a step_id, or None."""
        for node in self.nodes:
            if node.step_id == step_id:
                return node
        return None

    def get_outgoing_edges(self, step_id: str) -> list[WorkflowEdge]:
        """Return all edges originating from a step."""
        return [e for e in self.edges if e.source == step_id]

    def get_incoming_edges(self, step_id: str) -> list[WorkflowEdge]:
        """Return all edges targeting a step."""
        return [e for e in self.edges if e.target == step_id]


# ---------------------------------------------------------------------------
# Visual Workflow API
# ---------------------------------------------------------------------------


class VisualWorkflowAPI:
    """Bundle serialization, deserialization, graph, and validation
    for visual workflow editing.

    Parameters
    ---
    validator:
        Optional WorkflowValidator instance. If None, validation
        will use a default validator (without registry-aware checks
        unless a dispatcher is provided).
    """

    def __init__(
        self,
        validator: Optional[WorkflowValidator] = None,
    ) -> None:
        self._validator = validator

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def serialize(self, workflow: Workflow) -> dict[str, Any]:
        """Serialize a Workflow to a JSON-compatible dict.

        Reuses Workflow.to_dict() — this is a thin wrapper that
        exists so the visual editor has a stable API boundary.
        """
        return workflow.to_dict()

    def deserialize(self, data: dict[str, Any]) -> Workflow:
        """Deserialize a dict to a Workflow.

        Reuses Workflow.from_dict() — raises ValueError on invalid
        input.
        """
        return Workflow.from_dict(data)

    # ------------------------------------------------------------------
    # Graph representation
    # ------------------------------------------------------------------

    def to_graph(self, workflow: Workflow) -> WorkflowGraph:
        """Convert a Workflow to a node-edge graph for visual rendering.

        Each step becomes a node. Each ``depends_on`` entry becomes a
        directed edge from the dependency to the dependent step.
        """
        nodes: list[WorkflowNode] = []
        edges: list[WorkflowEdge] = []

        for step in workflow.steps:
            node = WorkflowNode(
                step_id=step.step_id,
                name=step.name or step.step_id,
                type=step.type.value,
                target=step.target,
                has_condition=step.condition is not None,
                inputs=dict(step.inputs),
                output_keys=list(step.output_keys),
            )
            nodes.append(node)

            # Create an edge for each dependency.
            for dep_id in step.depends_on:
                edge = WorkflowEdge(
                    source=dep_id,
                    target=step.step_id,
                )
                edges.append(edge)

        return WorkflowGraph(
            workflow_id=workflow.workflow_id,
            nodes=nodes,
            edges=edges,
        )

    def from_graph(
        self,
        graph: WorkflowGraph,
        *,
        name: str = "",
        description: str = "",
        variables: Optional[dict[str, Any]] = None,
        outputs: Optional[dict[str, str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Workflow:
        """Convert a node-edge graph back to a Workflow.

        This is the inverse of ``to_graph``. Note that some
        information is lost in the graph representation (conditions,
        retry policies, timeouts) — those are set to defaults.

        Parameters
        ----------
        graph:
            The graph to convert.
        name:
            Workflow name (not stored in the graph).
        description:
            Workflow description.
        variables:
            Initial variables (not stored in the graph).
        outputs:
            Workflow outputs (not stored in the graph).
        metadata:
            Workflow metadata.
        """
        # Build a lookup from step_id → node.
        node_map: dict[str, WorkflowNode] = {n.step_id: n for n in graph.nodes}

        # Build dependency map from edges: step_id → [dep_ids].
        dep_map: dict[str, list[str]] = {}
        for edge in graph.edges:
            dep_map.setdefault(edge.target, []).append(edge.source)

        steps: list[WorkflowStep] = []
        for node in graph.nodes:
            step = WorkflowStep(
                step_id=node.step_id,
                name=node.name,
                type=StepType(node.type),
                target=node.target,
                inputs=dict(node.inputs),
                output_keys=list(node.output_keys),
                depends_on=dep_map.get(node.step_id, []),
            )
            steps.append(step)

        return Workflow(
            workflow_id=graph.workflow_id,
            name=name,
            description=description,
            variables=dict(variables or {}),
            steps=steps,
            outputs=dict(outputs or {}),
            metadata=dict(metadata or {}),
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, workflow: Workflow) -> ValidationResult:
        """Validate a Workflow.

        Uses the injected WorkflowValidator if available, otherwise
        falls back to the structural-only validate_structure helper.
        """
        if self._validator is not None:
            return self._validator.validate(workflow)
        # Fall back to structural validation without registry checks.
        from workflows.validation import validate_structure

        return validate_structure(workflow)
