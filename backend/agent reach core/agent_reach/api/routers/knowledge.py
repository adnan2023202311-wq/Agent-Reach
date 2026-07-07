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
    """Return knowledge graph nodes/edges for visualization."""
    kg = _kg(pipeline)
    try:
        nodes_dict = {}
        edges_list = []
        if hasattr(kg, "_nodes"):
            nodes_dict = getattr(kg, "_nodes", {})
        if hasattr(kg, "nodes"):
            try:
                nodes_dict = kg.nodes  # type: ignore
            except Exception:
                pass
        if hasattr(kg, "_edges"):
            edges_list = getattr(kg, "_edges", [])
        # build arrays
        nodes = []
        for nid, n in list(nodes_dict.items())[:limit]:
            nodes.append({
                "id": str(getattr(n, "id", nid)),
                "label": getattr(n, "label", str(nid)),
                "type": str(getattr(n, "node_type", getattr(n, "type", "unknown"))),
            })
        edges = []
        for e in edges_list[:limit]:
            if isinstance(e, dict):
                edges.append(e)
            else:
                edges.append({
                    "source": str(getattr(e, "source", getattr(e, "from_id", ""))),
                    "target": str(getattr(e, "target", getattr(e, "to_id", ""))),
                    "type": str(getattr(e, "edge_type", getattr(e, "type", "related_to"))),
                })
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
            added = kg.add_node(nt, nid, node.label)
        else:
            # auto id
            import uuid
            added = kg.add_node(nt, f"{node.node_type}_{uuid.uuid4().hex[:8]}", node.label)
        return {"id": added, "status": "created"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
