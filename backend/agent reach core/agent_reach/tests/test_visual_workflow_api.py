"""Unit tests for VisualWorkflowAPI (M6.8)."""

from __future__ import annotations

import pytest

from visual_workflow.api import (
    VisualWorkflowAPI,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
)
from workflows.models import (
    Condition,
    ConditionOp,
    StepType,
    Workflow,
    WorkflowStep,
)


@pytest.fixture
def api() -> VisualWorkflowAPI:
    return VisualWorkflowAPI()


@pytest.fixture
def sample_workflow() -> Workflow:
    return Workflow(
        name="test-workflow",
        description="A test workflow",
        variables={"x": 10},
        steps=[
            WorkflowStep(
                step_id="s1",
                name="Research",
                type=StepType.AGENT,
                target="research",
                inputs={"q": "what is AI?"},
                output_keys=["text"],
            ),
            WorkflowStep(
                step_id="s2",
                name="Summarize",
                type=StepType.AGENT,
                target="coding",
                inputs={"text": "{{ outputs.s1.text }}"},
                output_keys=["summary"],
                depends_on=["s1"],
                condition=Condition("variables.x", ConditionOp.GT, value=5),
            ),
            WorkflowStep(
                step_id="s3",
                name="Final",
                type=StepType.TOOL,
                target="shout",
                inputs={"text": "{{ outputs.s2.summary }}"},
                output_keys=["result"],
                depends_on=["s2"],
            ),
        ],
        outputs={"final": "outputs.s3.result"},
    )


# ---------------------------------------------------------------------------
# Graph models
# ---------------------------------------------------------------------------


class TestGraphModels:
    def test_node_to_dict(self) -> None:
        node = WorkflowNode(
            step_id="s1",
            name="Research",
            type="agent",
            target="research",
        )
        d = node.to_dict()
        assert d["step_id"] == "s1"
        assert d["type"] == "agent"
        assert d["has_condition"] is False

    def test_edge_to_dict(self) -> None:
        edge = WorkflowEdge(source="s1", target="s2", label="dep")
        d = edge.to_dict()
        assert d == {"source": "s1", "target": "s2", "label": "dep"}

    def test_graph_to_dict(self) -> None:
        graph = WorkflowGraph(
            workflow_id="wf-1",
            nodes=[WorkflowNode(step_id="s1", name="A", type="agent", target="t")],
            edges=[],
        )
        d = graph.to_dict()
        assert d["workflow_id"] == "wf-1"
        assert len(d["nodes"]) == 1

    def test_graph_get_node(self) -> None:
        node = WorkflowNode(step_id="s1", name="A", type="agent", target="t")
        graph = WorkflowGraph(workflow_id="wf", nodes=[node], edges=[])
        assert graph.get_node("s1") is node
        assert graph.get_node("ghost") is None

    def test_graph_get_edges(self) -> None:
        edges = [
            WorkflowEdge(source="s1", target="s2"),
            WorkflowEdge(source="s2", target="s3"),
        ]
        graph = WorkflowGraph(workflow_id="wf", nodes=[], edges=edges)
        assert len(graph.get_outgoing_edges("s1")) == 1
        assert len(graph.get_incoming_edges("s2")) == 1
        assert len(graph.get_outgoing_edges("s3")) == 0


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_serialize(self, api: VisualWorkflowAPI, sample_workflow: Workflow) -> None:
        data = api.serialize(sample_workflow)
        assert data["name"] == "test-workflow"
        assert len(data["steps"]) == 3

    def test_deserialize(self, api: VisualWorkflowAPI, sample_workflow: Workflow) -> None:
        data = api.serialize(sample_workflow)
        restored = api.deserialize(data)
        assert restored.name == "test-workflow"
        assert len(restored.steps) == 3
        assert restored.steps[0].step_id == "s1"

    def test_deserialize_invalid_raises(self, api: VisualWorkflowAPI) -> None:
        with pytest.raises(ValueError):
            api.deserialize("not-a-dict")  # type: ignore[arg-type]

    def test_round_trip(self, api: VisualWorkflowAPI, sample_workflow: Workflow) -> None:
        data = api.serialize(sample_workflow)
        restored = api.deserialize(data)
        data2 = api.serialize(restored)
        assert data == data2


# ---------------------------------------------------------------------------
# Graph representation
# ---------------------------------------------------------------------------


class TestGraphRepresentation:
    def test_to_graph_creates_nodes(
        self, api: VisualWorkflowAPI, sample_workflow: Workflow
    ) -> None:
        graph = api.to_graph(sample_workflow)
        assert len(graph.nodes) == 3
        assert {n.step_id for n in graph.nodes} == {"s1", "s2", "s3"}

    def test_to_graph_creates_edges(
        self, api: VisualWorkflowAPI, sample_workflow: Workflow
    ) -> None:
        graph = api.to_graph(sample_workflow)
        # s2 depends on s1, s3 depends on s2 → 2 edges.
        assert len(graph.edges) == 2
        edge_pairs = {(e.source, e.target) for e in graph.edges}
        assert edge_pairs == {("s1", "s2"), ("s2", "s3")}

    def test_to_graph_node_metadata(
        self, api: VisualWorkflowAPI, sample_workflow: Workflow
    ) -> None:
        graph = api.to_graph(sample_workflow)
        s2 = graph.get_node("s2")
        assert s2 is not None
        assert s2.name == "Summarize"
        assert s2.has_condition is True
        assert s2.output_keys == ["summary"]

    def test_to_graph_empty_workflow(self, api: VisualWorkflowAPI) -> None:
        wf = Workflow(name="empty")
        graph = api.to_graph(wf)
        assert graph.nodes == []
        assert graph.edges == []

    def test_from_graph_round_trip(
        self, api: VisualWorkflowAPI, sample_workflow: Workflow
    ) -> None:
        graph = api.to_graph(sample_workflow)
        restored = api.from_graph(
            graph,
            name=sample_workflow.name,
            description=sample_workflow.description,
            variables=sample_workflow.variables,
            outputs=sample_workflow.outputs,
        )
        assert restored.name == sample_workflow.name
        assert len(restored.steps) == 3
        # Dependencies are preserved.
        s2 = next(s for s in restored.steps if s.step_id == "s2")
        assert s2.depends_on == ["s1"]

    def test_from_graph_preserves_structure(
        self, api: VisualWorkflowAPI
    ) -> None:
        graph = WorkflowGraph(
            workflow_id="wf-x",
            nodes=[
                WorkflowNode(step_id="a", name="A", type="agent", target="research"),
                WorkflowNode(step_id="b", name="B", type="tool", target="shout"),
            ],
            edges=[WorkflowEdge(source="a", target="b")],
        )
        wf = api.from_graph(graph, name="test")
        assert wf.name == "test"
        assert len(wf.steps) == 2
        assert wf.steps[1].depends_on == ["a"]

    def test_from_graph_node_without_edges(
        self, api: VisualWorkflowAPI
    ) -> None:
        graph = WorkflowGraph(
            workflow_id="wf-y",
            nodes=[WorkflowNode(step_id="only", name="Only", type="agent", target="t")],
            edges=[],
        )
        wf = api.from_graph(graph)
        assert len(wf.steps) == 1
        assert wf.steps[0].depends_on == []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_validate_valid_workflow(
        self, api: VisualWorkflowAPI, sample_workflow: Workflow
    ) -> None:
        result = api.validate(sample_workflow)
        assert result.valid is True

    def test_validate_invalid_workflow(self, api: VisualWorkflowAPI) -> None:
        # Workflow with a cycle.
        wf = Workflow(
            name="bad",
            steps=[
                WorkflowStep(step_id="a", type=StepType.AGENT, target="research", depends_on=["b"]),
                WorkflowStep(step_id="b", type=StepType.AGENT, target="research", depends_on=["a"]),
            ],
        )
        result = api.validate(wf)
        assert result.valid is False

    def test_validate_empty_name(self, api: VisualWorkflowAPI) -> None:
        wf = Workflow(name="", steps=[WorkflowStep(step_id="s1", type=StepType.AGENT, target="research")])
        result = api.validate(wf)
        assert result.valid is False
