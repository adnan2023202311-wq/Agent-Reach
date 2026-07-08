"""
Self-Evolving Knowledge Graph (M9.18).

Layer: Application — composes the EXISTING KnowledgeGraph (M7 +
M9.8 confidence/versioning). It does not store anything itself.

What "self-evolving" means here, concretely and honestly:

- Automatic entity discovery: deterministic extraction of candidate
  entities from execution text (capitalized multi-word phrases,
  quoted terms, code identifiers). Rule-based extraction is exact
  about what it can and cannot find — it is not presented as NLU.
- Relationship extraction: entities co-occurring in the same text
  are linked (RELATED_TO); entities are linked to the execution they
  came from (LEARNED_FROM) so provenance is queryable.
- Confidence scoring & refinement: a newly discovered entity starts
  at low confidence; every re-observation raises confidence along a
  bounded curve (asymptotic to 1.0) using the graph's M9.8
  update_node — which also gives versioning and history for free.
- Historical evolution: get_node_history() on any discovered entity
  shows its confidence trajectory across observations.

The engine plugs into the IntelligentPipeline's existing knowledge
step via composition (pipeline calls observe_execution when an
evolution engine is attached) — no parallel KG write path.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from knowledge.graph import EdgeType, KnowledgeGraph, NodeType

# Discovery parameters — documented, deterministic.
_INITIAL_CONFIDENCE = 0.3
_CONFIDENCE_GAIN = 0.2  # each re-observation closes 20% of the gap to 1.0
_MIN_ENTITY_LENGTH = 3
_MAX_ENTITIES_PER_TEXT = 25

# Capitalized phrases: 2–4 Capitalized words in sequence ("Knowledge
# Graph", "Agent Reach"). The repetition is bounded so a long run of
# capitalized words yields several bounded phrases instead of one
# unbounded blob. Leading determiners are stripped post-match.
_CAPITALIZED_PHRASE = re.compile(
    r"\b([A-Z][a-zA-Z0-9]+(?:[ \-][A-Z][a-zA-Z0-9]+){1,3})\b"
)
_LEADING_DETERMINER = re.compile(r"^(?:The|A|An)\s+")
# Quoted terms: 'thing' or "thing"
_QUOTED_TERM = re.compile(r"[\"']([A-Za-z][A-Za-z0-9 _\-]{2,40})[\"']")
# Code identifiers: snake_case or CamelCase words of length ≥ 6
_CODE_IDENTIFIER = re.compile(
    r"\b([a-z][a-z0-9]+(?:_[a-z0-9]+)+|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+)\b"
)

_STOPWORD_PHRASES = {
    "I Am", "It Is", "This Is", "That Is", "There Are", "The The",
}


def extract_entities(text: str, max_entities: int = _MAX_ENTITIES_PER_TEXT) -> list[str]:
    """Deterministically extract candidate entity labels from text.

    Order of discovery is preserved; duplicates (case-insensitive)
    removed; bounded by max_entities.
    """
    candidates: list[str] = []
    for pattern in (_CAPITALIZED_PHRASE, _QUOTED_TERM, _CODE_IDENTIFIER):
        candidates.extend(pattern.findall(text))

    seen: set[str] = set()
    entities: list[str] = []
    for candidate in candidates:
        label = _LEADING_DETERMINER.sub("", candidate.strip())
        # A determiner-only match ("The") strips to a single word that
        # no longer satisfies the multi-word phrase pattern — keep it
        # only if it still looks like an entity (≥ 2 words or an
        # identifier); single capitalized words are too noisy.
        if " " in candidate and " " not in label and "_" not in label:
            continue
        key = label.lower()
        if len(label) < _MIN_ENTITY_LENGTH:
            continue
        if label in _STOPWORD_PHRASES:
            continue
        if key in seen:
            continue
        seen.add(key)
        entities.append(label)
        if len(entities) >= max_entities:
            break
    return entities


@dataclass
class ObservationResult:
    """What one observe_execution() call did to the graph."""

    entities_discovered: list[str] = field(default_factory=list)
    entities_reinforced: list[str] = field(default_factory=list)
    relationships_added: int = 0
    execution_node_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities_discovered": list(self.entities_discovered),
            "entities_reinforced": list(self.entities_reinforced),
            "relationships_added": self.relationships_added,
            "execution_node_id": self.execution_node_id,
        }


class KnowledgeEvolutionEngine:
    """Evolve the SHARED KnowledgeGraph from execution text."""

    def __init__(self, graph: KnowledgeGraph) -> None:
        self._graph = graph
        self._observations = 0

    @property
    def graph(self) -> KnowledgeGraph:
        return self._graph

    # ── Observation ─────────────────────────────────────────────

    def observe_execution(
        self,
        text: str,
        request_id: str = "",
        execution_node_id: Optional[str] = None,
    ) -> ObservationResult:
        """Discover/reinforce entities from one execution's text.

        - New entities enter at low confidence (v1).
        - Known entities (matched by stable entity id) get a bounded
          confidence increase recorded as a new version.
        - Co-occurring entities are linked RELATED_TO (deduplicated).
        - When an execution node id is provided, every entity in this
          text is linked to it LEARNED_FROM (provenance).
        """
        self._observations += 1
        result = ObservationResult(execution_node_id=execution_node_id)
        labels = extract_entities(text)
        node_ids: list[str] = []

        for label in labels:
            entity_id = self._entity_id(label)
            existing = self._graph.get_node(entity_id)
            if existing is None:
                self._graph.add_node(
                    NodeType.ENTITY,
                    label,
                    description=f"Discovered from execution {request_id}".strip(),
                    properties={"observations": 1, "first_request_id": request_id},
                    node_id=entity_id,
                    confidence=_INITIAL_CONFIDENCE,
                )
                result.entities_discovered.append(label)
            else:
                observations = int(existing.properties.get("observations", 1)) + 1
                new_confidence = existing.confidence + _CONFIDENCE_GAIN * (
                    1.0 - existing.confidence
                )
                self._graph.update_node(
                    entity_id,
                    properties={"observations": observations,
                                "last_request_id": request_id},
                    confidence=new_confidence,
                )
                result.entities_reinforced.append(label)
            node_ids.append(entity_id)

        # Relationships: link co-occurring entities pairwise (bounded
        # chain rather than full clique to keep edge growth linear).
        for source, target in zip(node_ids, node_ids[1:]):
            if not self._edge_exists(source, target, EdgeType.RELATED_TO):
                edge_id = self._graph.add_edge(source, target, EdgeType.RELATED_TO)
                if edge_id:
                    result.relationships_added += 1

        # Provenance links to the execution node.
        if execution_node_id and self._graph.get_node(execution_node_id):
            for node_id in node_ids:
                if not self._edge_exists(
                    node_id, execution_node_id, EdgeType.LEARNED_FROM
                ):
                    edge_id = self._graph.add_edge(
                        node_id, execution_node_id, EdgeType.LEARNED_FROM
                    )
                    if edge_id:
                        result.relationships_added += 1
        return result

    # ── Introspection ───────────────────────────────────────────

    def get_discovered_entities(
        self, min_confidence: float = 0.0, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Discovered entities, most-confident first."""
        entities = [
            node
            for node in self._graph.get_by_type(NodeType.ENTITY)
            if node.confidence >= min_confidence
        ]
        entities.sort(key=lambda n: (n.confidence, n.version), reverse=True)
        return [node.to_dict() for node in entities[: max(0, limit)]]

    def get_evolution(self, label_or_id: str) -> dict[str, Any]:
        """One entity's full evolution: current state + history."""
        entity_id = (
            label_or_id
            if self._graph.get_node(label_or_id) is not None
            else self._entity_id(label_or_id)
        )
        node = self._graph.get_node(entity_id)
        if node is None:
            raise KeyError(f"Entity '{label_or_id}' not found")
        return {
            "current": node.to_dict(),
            "history": self._graph.get_node_history(entity_id),
            "observations": int(node.properties.get("observations", 1)),
        }

    def get_stats(self) -> dict[str, Any]:
        entities = self._graph.get_by_type(NodeType.ENTITY)
        return {
            "observations": self._observations,
            "total_entities": len(entities),
            "avg_confidence": (
                sum(n.confidence for n in entities) / len(entities)
                if entities
                else 0.0
            ),
            "high_confidence_entities": sum(
                1 for n in entities if n.confidence >= 0.7
            ),
        }

    # ── Internals ───────────────────────────────────────────────

    @staticmethod
    def _entity_id(label: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        return f"entity_{normalized}"

    def _edge_exists(self, source: str, target: str, edge_type: EdgeType) -> bool:
        return any(
            edge.target_id == target and edge.edge_type == edge_type
            for _, edge, direction in self._graph.get_neighbors(
                source, direction="outgoing"
            )
        )
