"""Tests for M9.8 — Runtime Knowledge Graph.

Covers the KnowledgeGraph extensions — confidence, versioning +
history, entity search, DOCUMENT/ENTITY node types — and the new
/api/v1/knowledge endpoints (update, history, neighbors), plus the
previously broken /nodes and /upload paths that referenced a
NodeType.DOCUMENT that didn't exist.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from config.settings import get_settings
from knowledge.graph import EdgeType, KnowledgeGraph, NodeType


# ===========================================================================
# Engine: confidence & versioning
# ===========================================================================


class TestConfidenceAndVersioning:
    def test_new_node_defaults(self) -> None:
        kg = KnowledgeGraph()
        nid = kg.add_node(NodeType.ENTITY, "Quantum Computing")
        node = kg.get_node(nid)
        assert node.confidence == 1.0
        assert node.version == 1
        assert kg.get_node_history(nid) == []

    def test_confidence_clamped(self) -> None:
        kg = KnowledgeGraph()
        low = kg.add_node(NodeType.ENTITY, "A", confidence=-3.0)
        high = kg.add_node(NodeType.ENTITY, "B", confidence=7.0)
        assert kg.get_node(low).confidence == 0.0
        assert kg.get_node(high).confidence == 1.0

    def test_update_bumps_version_and_records_history(self) -> None:
        kg = KnowledgeGraph()
        nid = kg.add_node(NodeType.ENTITY, "LLM", description="v1 desc")
        kg.update_node(nid, description="v2 desc", confidence=0.7)
        node = kg.get_node(nid)
        assert node.version == 2
        assert node.description == "v2 desc"
        assert node.confidence == 0.7
        history = kg.get_node_history(nid)
        assert len(history) == 1
        assert history[0]["description"] == "v1 desc"
        assert history[0]["version"] == 1

    def test_partial_update_preserves_other_fields(self) -> None:
        kg = KnowledgeGraph()
        nid = kg.add_node(
            NodeType.ENTITY, "GraphRAG", description="keep", properties={"a": 1}
        )
        kg.update_node(nid, label="GraphRAG v2")
        node = kg.get_node(nid)
        assert node.description == "keep"
        assert node.properties == {"a": 1}

    def test_update_unknown_raises(self) -> None:
        kg = KnowledgeGraph()
        with pytest.raises(KeyError):
            kg.update_node("ghost", label="x")

    def test_re_add_same_id_versions_instead_of_overwriting(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(NodeType.AGENT, "agent v1", node_id="agent_1")
        kg.add_node(NodeType.AGENT, "agent v2", node_id="agent_1")
        node = kg.get_node("agent_1")
        assert node.version == 2
        assert node.label == "agent v2"
        assert len(kg.get_node_history("agent_1")) == 1
        # No duplicate in the type index / node count.
        assert kg.get_stats()["total_nodes"] == 1

    def test_remove_node_drops_history(self) -> None:
        kg = KnowledgeGraph()
        nid = kg.add_node(NodeType.ENTITY, "temp")
        kg.update_node(nid, label="temp2")
        kg.remove_node(nid)
        assert kg.get_node_history(nid) == []

    def test_clear_drops_history(self) -> None:
        kg = KnowledgeGraph()
        nid = kg.add_node(NodeType.ENTITY, "temp")
        kg.update_node(nid, label="x")
        kg.clear()
        assert kg.get_node_history(nid) == []


# ===========================================================================
# Engine: search
# ===========================================================================


class TestGraphSearch:
    def _populated(self) -> KnowledgeGraph:
        kg = KnowledgeGraph()
        kg.add_node(
            NodeType.ENTITY,
            "Transformer Architecture",
            description="Attention-based neural networks",
        )
        kg.add_node(
            NodeType.ENTITY,
            "Convolutional Networks",
            description="Image processing models",
            properties={"domain": "vision transformers"},
        )
        kg.add_node(NodeType.AGENT, "research_agent", description="Does research")
        return kg

    def test_label_match_ranks_highest(self) -> None:
        kg = self._populated()
        results = kg.search("transformer")
        assert len(results) == 2
        assert results[0].label == "Transformer Architecture"

    def test_confidence_weights_ranking(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(NodeType.ENTITY, "python guide", confidence=0.2)
        strong = kg.add_node(NodeType.ENTITY, "python handbook", confidence=1.0)
        results = kg.search("python")
        assert results[0].id == strong

    def test_empty_query_returns_nothing(self) -> None:
        kg = self._populated()
        assert kg.search("") == []
        assert kg.search("   ") == []

    def test_no_match_returns_empty(self) -> None:
        kg = self._populated()
        assert kg.search("blockchain") == []

    def test_limit_respected(self) -> None:
        kg = KnowledgeGraph()
        for i in range(10):
            kg.add_node(NodeType.ENTITY, f"topic {i}")
        assert len(kg.search("topic", limit=3)) == 3


# ===========================================================================
# API
# ===========================================================================


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    import config.settings as settings_module

    original = settings_module.get_settings
    settings_module.get_settings = lambda: settings_module.Settings(
        anthropic_api_key=None,
        default_model_provider="anthropic",
    )
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    settings_module.get_settings = original
    get_settings.cache_clear()


def _create_node(client: TestClient, label: str, **extra) -> str:
    resp = client.post(
        "/api/v1/knowledge/nodes", json={"label": label, **extra}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


class TestKnowledgeAPI:
    def test_create_document_node_works_now(self, client: TestClient) -> None:
        """The M8 handler referenced NodeType.DOCUMENT which didn't
        exist — creating a document node must succeed now."""
        nid = _create_node(client, "Design Doc", node_type="document")
        assert nid

    def test_create_with_confidence(self, client: TestClient) -> None:
        nid = _create_node(client, "Uncertain Entity", node_type="entity", confidence=0.4)
        graph = client.get("/api/v1/knowledge/graph").json()
        node = next(n for n in graph["nodes"] if n["id"] == nid)
        assert node["confidence"] == 0.4
        assert node["version"] == 1

    def test_update_and_history(self, client: TestClient) -> None:
        nid = _create_node(client, "Evolving Node", node_type="entity")
        patch = client.patch(
            f"/api/v1/knowledge/nodes/{nid}",
            json={"label": "Evolved Node", "confidence": 0.9},
        )
        assert patch.status_code == 200
        assert patch.json()["version"] == 2

        history = client.get(f"/api/v1/knowledge/nodes/{nid}/history").json()
        assert history["versions"] == 2
        assert len(history["history"]) == 1
        assert history["history"][0]["label"] == "Evolving Node"
        assert history["current"]["label"] == "Evolved Node"

    def test_update_unknown_404(self, client: TestClient) -> None:
        resp = client.patch("/api/v1/knowledge/nodes/ghost", json={"label": "x"})
        assert resp.status_code == 404

    def test_history_unknown_404(self, client: TestClient) -> None:
        assert client.get("/api/v1/knowledge/nodes/ghost/history").status_code == 404

    def test_invalid_confidence_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/knowledge/nodes",
            json={"label": "bad", "confidence": 2.5},
        )
        assert resp.status_code == 422

    def test_neighbors_exploration(self, client: TestClient) -> None:
        a = _create_node(client, "Source Node", node_type="entity")
        b = _create_node(client, "Target Node", node_type="entity")
        # Create the relationship directly through the shared engine —
        # edges have no POST endpoint yet; pipeline state is shared.
        # (The graph endpoint proves both nodes exist server-side.)
        graph_before = client.get("/api/v1/knowledge/graph").json()
        ids = {n["id"] for n in graph_before["nodes"]}
        assert {a, b} <= ids

        resp = client.get(f"/api/v1/knowledge/nodes/{a}/neighbors")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0  # honest zero — no edges yet

    def test_neighbors_invalid_direction_422(self, client: TestClient) -> None:
        nid = _create_node(client, "Directional", node_type="entity")
        resp = client.get(f"/api/v1/knowledge/nodes/{nid}/neighbors?direction=sideways")
        assert resp.status_code == 422

    def test_neighbors_unknown_404(self, client: TestClient) -> None:
        assert client.get("/api/v1/knowledge/nodes/ghost/neighbors").status_code == 404

    def test_search_uses_real_engine(self, client: TestClient) -> None:
        _create_node(client, "Retrieval Augmented Generation", node_type="entity")
        resp = client.post(
            "/api/v1/knowledge/search",
            json={"query": "retrieval augmented"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        assert any("Retrieval" in r["label"] for r in data["results"])

    def test_upload_document(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("notes.txt", b"knowledge content here", "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "indexed"
        assert data["filename"] == "notes.txt"
