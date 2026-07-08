"""Tests for M9.18 — Self-Evolving Knowledge Graph.

Proves: deterministic entity extraction (documented patterns only),
low-confidence entry + bounded reinforcement via the M9.8 versioning
path, relationship + provenance links, historical evolution, pipeline
integration through the existing knowledge step, and the API.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from composition import build_intelligent_pipeline
from config.settings import get_settings
from knowledge.evolution import (
    KnowledgeEvolutionEngine,
    extract_entities,
)
from knowledge.graph import EdgeType, KnowledgeGraph, NodeType


# ===========================================================================
# Extraction
# ===========================================================================


class TestExtraction:
    def test_capitalized_phrases(self) -> None:
        entities = extract_entities(
            "The Knowledge Graph feeds Agent Reach with facts."
        )
        assert "Knowledge Graph" in entities
        assert "Agent Reach" in entities

    def test_quoted_terms(self) -> None:
        entities = extract_entities("The tool named 'vector search' was used.")
        assert "vector search" in entities

    def test_code_identifiers(self) -> None:
        entities = extract_entities(
            "Call intelligent_pipeline then ReflectionEngine."
        )
        assert "intelligent_pipeline" in entities
        assert "ReflectionEngine" in entities

    def test_deduplication_case_insensitive(self) -> None:
        entities = extract_entities("Agent Reach and AGENT REACH and Agent Reach")
        lowered = [e.lower() for e in entities]
        assert lowered.count("agent reach") == 1

    def test_bounded(self) -> None:
        text = " ".join(f"Entity Number{i} Alpha{i}" for i in range(100))
        assert len(extract_entities(text, max_entities=10)) == 10

    def test_no_entities_in_plain_text(self) -> None:
        assert extract_entities("just plain lowercase words here") == []


# ===========================================================================
# Evolution engine
# ===========================================================================


class TestEvolution:
    def test_discovery_enters_at_low_confidence(self) -> None:
        engine = KnowledgeEvolutionEngine(KnowledgeGraph())
        result = engine.observe_execution(
            "Research about Quantum Computing basics", request_id="r1"
        )
        assert "Quantum Computing" in result.entities_discovered
        entity = engine.graph.get_node("entity_quantum_computing")
        assert entity.confidence == pytest.approx(0.3)
        assert entity.version == 1

    def test_reinforcement_raises_confidence_bounded(self) -> None:
        engine = KnowledgeEvolutionEngine(KnowledgeGraph())
        engine.observe_execution("a note on Quantum Computing", request_id="r1")
        confidences = []
        for i in range(10):
            engine.observe_execution(
                "more about Quantum Computing", request_id=f"r{i+2}"
            )
            confidences.append(
                engine.graph.get_node("entity_quantum_computing").confidence
            )
        # strictly increasing, asymptotic to 1.0, never exceeding it
        assert all(b > a for a, b in zip(confidences, confidences[1:]))
        assert confidences[-1] < 1.0
        # versioned via the M9.8 path — full history retained
        evolution = engine.get_evolution("Quantum Computing")
        assert evolution["observations"] == 11
        assert len(evolution["history"]) == 10

    def test_cooccurrence_links_related(self) -> None:
        engine = KnowledgeEvolutionEngine(KnowledgeGraph())
        result = engine.observe_execution(
            "Vector Databases power Retrieval Augmentation", request_id="r1"
        )
        assert result.relationships_added >= 1
        neighbors = engine.graph.get_neighbors(
            "entity_vector_databases", direction="outgoing"
        )
        targets = {edge.target_id for _, edge, _ in neighbors}
        assert "entity_retrieval_augmentation" in targets

    def test_no_duplicate_edges_on_reobservation(self) -> None:
        engine = KnowledgeEvolutionEngine(KnowledgeGraph())
        engine.observe_execution("Vector Databases and Retrieval Augmentation", request_id="r1")
        second = engine.observe_execution(
            "Vector Databases and Retrieval Augmentation", request_id="r2"
        )
        assert second.relationships_added == 0

    def test_provenance_links_to_execution_node(self) -> None:
        graph = KnowledgeGraph()
        exec_id = graph.add_node(NodeType.EXECUTION, "exec_1", "run")
        engine = KnowledgeEvolutionEngine(graph)
        engine.observe_execution(
            "Learned about Semantic Routing", request_id="r1",
            execution_node_id=exec_id,
        )
        neighbors = graph.get_neighbors("entity_semantic_routing", direction="outgoing")
        learned = [
            edge for _, edge, _ in neighbors
            if edge.edge_type == EdgeType.LEARNED_FROM
        ]
        assert len(learned) == 1
        assert learned[0].target_id == exec_id

    def test_get_evolution_unknown_raises(self) -> None:
        engine = KnowledgeEvolutionEngine(KnowledgeGraph())
        with pytest.raises(KeyError):
            engine.get_evolution("Nonexistent Thing")

    def test_stats_honest(self) -> None:
        engine = KnowledgeEvolutionEngine(KnowledgeGraph())
        assert engine.get_stats()["total_entities"] == 0
        engine.observe_execution("About Graph Theory", request_id="r1")
        stats = engine.get_stats()
        assert stats["total_entities"] == 1
        assert stats["observations"] == 1


# ===========================================================================
# Pipeline integration
# ===========================================================================


@pytest.mark.asyncio
class TestPipelineIntegration:
    async def test_execution_evolves_shared_graph(self) -> None:
        pipeline = build_intelligent_pipeline()
        await pipeline.process("Research Quantum Computing and Machine Learning")
        evolution = pipeline._get_knowledge_evolution()
        assert evolution is not None
        # The evolution engine writes into the SAME graph instance.
        assert evolution.graph is pipeline._get_knowledge_graph()
        # MockModelClient echoes the prompt → entities get discovered.
        entities = evolution.get_discovered_entities()
        assert len(entities) >= 1

    async def test_trace_counts_include_evolution(self) -> None:
        pipeline = build_intelligent_pipeline()
        result = await pipeline.process("Analyze Distributed Systems patterns")
        # base step adds 1 exec node + agent nodes; evolution adds more
        assert result.trace.kg_nodes_added >= 2


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


class TestEvolutionAPI:
    def test_entities_endpoint_after_chat(self, client: TestClient) -> None:
        client.post(
            "/api/v1/chat",
            json={"message": "Tell me about Neural Networks and Deep Learning"},
        )
        data = client.get("/api/v1/knowledge/evolution/entities").json()
        assert data["count"] >= 1
        assert data["stats"]["observations"] >= 1

    def test_entity_detail_by_label(self, client: TestClient) -> None:
        client.post(
            "/api/v1/chat",
            json={"message": "Explain Graph Databases in detail"},
        )
        entities = client.get("/api/v1/knowledge/evolution/entities").json()["entities"]
        assert entities, "expected at least one discovered entity"
        label = entities[0]["label"]
        detail = client.get(f"/api/v1/knowledge/evolution/entities/{label}")
        assert detail.status_code == 200
        assert detail.json()["observations"] >= 1

    def test_entity_detail_unknown_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/knowledge/evolution/entities/Totally Unknown")
        assert resp.status_code == 404

    def test_min_confidence_filter(self, client: TestClient) -> None:
        client.post(
            "/api/v1/chat", json={"message": "Discuss Edge Computing trends"}
        )
        strict = client.get(
            "/api/v1/knowledge/evolution/entities?min_confidence=0.99"
        ).json()
        # fresh entities start at 0.3 — none can pass a 0.99 floor
        assert strict["count"] == 0
