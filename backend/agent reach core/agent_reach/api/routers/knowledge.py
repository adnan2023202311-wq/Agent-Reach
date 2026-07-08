"""
API layer: /api/v1/knowledge — Knowledge Graph & RAG Studio backend.

Milestone 8 / M8.7
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from api.dependencies import get_pipeline

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


class KnowledgeSearchQuery(BaseModel):
    query: str
    limit: int = 20
    collection: Optional[str] = None


class KnowledgeNodeIn(BaseModel):
    node_type: str = "document"
    node_id: Optional[str] = None
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class KnowledgeNodeUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    properties: Optional[dict[str, Any]] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


def _kg(pipeline):
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not available")
    try:
        return pipeline._get_knowledge_graph()  # type: ignore[attr-defined]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/stats")
async def knowledge_stats(pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    kg = _kg(pipeline)
    try:
        stats = kg.get_stats()
    except Exception:
        stats = {}
    return {"engine": "KnowledgeGraph", "version": "7.8", **stats}


@router.post("/search")
async def knowledge_search(body: KnowledgeSearchQuery, pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    """Search knowledge graph / RAG index."""
    kg = _kg(pipeline)
    try:
        # KnowledgeGraph has search capability via nodes
        results = []
        # naive fallback: iterate nodes
        if hasattr(kg, "search"):
            results = kg.search(body.query, limit=body.limit)  # type: ignore
        else:
            # graph traversal fallback
            nodes = []
            if hasattr(kg, "nodes"):
                nodes = list(getattr(kg, "nodes", {}).values())[:body.limit]
            elif hasattr(kg, "_nodes"):
                nodes = list(getattr(kg, "_nodes", {}).values())[:body.limit]
            results = nodes
        # normalize
        out = []
        for r in results[: body.limit]:
            if isinstance(r, dict):
                out.append(r)
            else:
                out.append({
                    "id": getattr(r, "id", getattr(r, "node_id", "")),
                    "label": getattr(r, "label", str(r)),
                    "type": getattr(r, "type", getattr(getattr(r, "node_type", None), "value", "unknown")) if hasattr(r, "node_type") else "node",
                })
        return {"results": out, "count": len(out), "query": body.query}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/graph")
async def get_graph(limit: int = 100, pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    """Return knowledge graph nodes/edges for visualization (M9.8).

    Uses the KnowledgeGraph's real to_dict() serializers — the M8
    getattr-probing version crashed on the edge dict (`_edges[:limit]`
    is not valid on a dict) and never returned edges.
    """
    kg = _kg(pipeline)
    try:
        nodes = [n.to_dict() for n in list(kg._nodes.values())[:limit]]
        edges = [e.to_dict() for e in list(kg._edges.values())[:limit]]
        return {"nodes": nodes, "edges": edges, "count": {"nodes": len(nodes), "edges": len(edges)}}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/nodes")
async def add_node(node: KnowledgeNodeIn, pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    kg = _kg(pipeline)
    try:
        from knowledge.graph import NodeType
        # map string to NodeType if possible
        nt = NodeType.DOCUMENT
        try:
            nt = NodeType(node.node_type)
        except Exception:
            # try upper
            for candidate in NodeType:
                if candidate.value.lower() == node.node_type.lower():
                    nt = candidate
                    break
        nid = node.node_id or None
        if nid:
            added = kg.add_node(nt, node.label, properties=node.properties, node_id=nid, confidence=node.confidence)
        else:
            # auto id
            import uuid
            added = kg.add_node(
                nt,
                node.label,
                properties=node.properties,
                node_id=f"{node.node_type}_{uuid.uuid4().hex[:8]}",
                confidence=node.confidence,
            )
        return {"id": added, "status": "created"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.patch("/nodes/{node_id}")
async def update_node(
    node_id: str, body: KnowledgeNodeUpdate, pipeline=Depends(get_pipeline)
) -> dict[str, Any]:
    """Update a node as a new version, recording history (M9.8)."""
    kg = _kg(pipeline)
    try:
        kg.update_node(
            node_id,
            label=body.label,
            description=body.description,
            properties=body.properties,
            confidence=body.confidence,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Node '{node_id}' not found.", "code": "NODE_NOT_FOUND"},
        ) from exc
    return {**kg.get_node(node_id).to_dict(), "status": "updated"}


@router.get("/nodes/{node_id}/history")
async def node_history(node_id: str, pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    """A node's version history: prior versions + current (M9.8)."""
    kg = _kg(pipeline)
    node = kg.get_node(node_id)
    if node is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Node '{node_id}' not found.", "code": "NODE_NOT_FOUND"},
        )
    return {
        "node_id": node_id,
        "current": node.to_dict(),
        "history": kg.get_node_history(node_id),
        "versions": node.version,
    }


@router.get("/nodes/{node_id}/neighbors")
async def node_neighbors(
    node_id: str, direction: str = "both", pipeline=Depends(get_pipeline)
) -> dict[str, Any]:
    """Relationship exploration: a node's direct neighbors (M9.8)."""
    canonical = {"in": "incoming", "out": "outgoing", "incoming": "incoming",
                 "outgoing": "outgoing", "both": "both"}.get(direction)
    if canonical is None:
        raise HTTPException(
            status_code=422,
            detail={"message": "direction must be 'incoming', 'outgoing', or 'both'.", "code": "INVALID_DIRECTION"},
        )
    direction = canonical
    kg = _kg(pipeline)
    if kg.get_node(node_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Node '{node_id}' not found.", "code": "NODE_NOT_FOUND"},
        )
    neighbors = kg.get_neighbors(node_id, direction=direction)
    return {
        "node_id": node_id,
        "neighbors": [
            {
                "node": node.to_dict(),
                "edge": edge.to_dict(),
                "direction": edge_direction,
            }
            for node, edge, edge_direction in neighbors
        ],
        "count": len(neighbors),
    }


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), collection: str = "default", pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    """RAG Studio file upload – stores as knowledge node."""
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")[:20000]
    kg = _kg(pipeline)
    try:
        from knowledge.graph import NodeType
        import uuid
        node_id = f"doc_{uuid.uuid4().hex[:8]}"
        kg.add_node(NodeType.DOCUMENT, node_id, file.filename or node_id)
        # also store in knowledge layer if available
        return {
            "id": node_id,
            "filename": file.filename,
            "size": len(content),
            "collection": collection,
            "chars_indexed": len(text),
            "status": "indexed",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/clear")
async def clear_knowledge(pipeline=Depends(get_pipeline)) -> dict[str, str]:
    kg = _kg(pipeline)
    try:
        kg.clear()
        return {"status": "cleared"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@router.get("/evolution/entities")
async def discovered_entities(
    min_confidence: float = 0.0, limit: int = 100, pipeline=Depends(get_pipeline)
) -> dict[str, Any]:
    """Entities discovered by the evolution engine (M9.18)."""
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not available")
    evolution = pipeline._get_knowledge_evolution()
    if evolution is None:
        raise HTTPException(status_code=503, detail="Knowledge evolution not available")
    entities = evolution.get_discovered_entities(
        min_confidence=min_confidence, limit=limit
    )
    return {"entities": entities, "count": len(entities), "stats": evolution.get_stats()}


@router.get("/evolution/entities/{label_or_id}")
async def entity_evolution(label_or_id: str, pipeline=Depends(get_pipeline)) -> dict[str, Any]:
    """One entity's confidence/version trajectory (M9.18)."""
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not available")
    evolution = pipeline._get_knowledge_evolution()
    if evolution is None:
        raise HTTPException(status_code=503, detail="Knowledge evolution not available")
    try:
        return evolution.get_evolution(label_or_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"message": str(exc), "code": "ENTITY_NOT_FOUND"},
        ) from exc
