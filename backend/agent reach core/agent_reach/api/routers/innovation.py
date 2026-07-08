"""
API layer: /api/v1/innovation — Research Engine & Innovation Watch
(M9.16 / M9.31).

Layer: Interface/Presentation.

Exposes the InnovationWatch: source management, scanning through the
real tool runtime, ranked findings, model evaluation (advisory), and
compatibility reports against the M9.26 adapter contracts. Never
deploys anything.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/innovation", tags=["innovation"])


class SourceCreate(BaseModel):
    url: str = Field(min_length=1)
    kind: str = "rss"
    label: str = ""


def _watch(request: Request):
    watch = getattr(request.app.state, "innovation_watch", None)
    if watch is None:
        raise HTTPException(status_code=503, detail="Innovation watch not available")
    return watch


@router.get("/sources")
async def list_sources(request: Request) -> dict[str, Any]:
    sources = _watch(request).list_sources()
    return {"sources": [s.to_dict() for s in sources], "count": len(sources)}


@router.post("/sources")
async def add_source(body: SourceCreate, request: Request) -> dict[str, Any]:
    try:
        return _watch(request).add_source(body.url, kind=body.kind, label=body.label).to_dict()
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "code": "INVALID_SOURCE"},
        ) from exc


@router.delete("/sources/{source_id}")
async def remove_source(source_id: str, request: Request) -> dict[str, Any]:
    if not _watch(request).remove_source(source_id):
        raise HTTPException(
            status_code=404,
            detail={"message": f"Source '{source_id}' not found.", "code": "SOURCE_NOT_FOUND"},
        )
    return {"source_id": source_id, "status": "removed"}


@router.post("/scan")
async def scan(request: Request) -> dict[str, Any]:
    """Fetch every source through the real tools; register findings."""
    return await _watch(request).scan()


@router.get("/findings")
async def list_findings(request: Request, topic: str = "", limit: int = 50) -> dict[str, Any]:
    findings = _watch(request).list_findings(topic=topic, limit=limit)
    return {"findings": [f.to_dict() for f in findings], "count": len(findings)}


@router.get("/findings/{finding_id}")
async def get_finding(finding_id: str, request: Request) -> dict[str, Any]:
    finding = _watch(request).get_finding(finding_id)
    if finding is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Finding '{finding_id}' not found.", "code": "FINDING_NOT_FOUND"},
        )
    return finding.to_dict()


@router.post("/findings/{finding_id}/evaluate")
async def evaluate_finding(finding_id: str, request: Request) -> dict[str, Any]:
    """Model evaluation (advisory, trace-linked)."""
    try:
        finding = await _watch(request).evaluate(finding_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"message": str(exc.args[0]), "code": "FINDING_NOT_FOUND"},
        ) from exc
    return finding.to_dict()


@router.get("/findings/{finding_id}/compatibility")
async def compatibility_report(finding_id: str, request: Request) -> dict[str, Any]:
    """Integration plan against the M9.26 adapter contracts."""
    try:
        return _watch(request).compatibility_report(finding_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"message": str(exc.args[0]), "code": "FINDING_NOT_FOUND"},
        ) from exc


@router.get("/stats")
async def innovation_stats(request: Request) -> dict[str, Any]:
    return _watch(request).get_stats()
