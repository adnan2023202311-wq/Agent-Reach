"""
API layer: /api/v1/auto-integration — Intelligent Auto Integration (M9.17).

Layer: Interface/Presentation.

Exposes the AutoIntegrationEngine: compatibility analysis (curated
technologies + declared capabilities), adapter scaffold generation
(returned for review — never executed server-side), static scaffold
validation, and persisted reports.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from infrastructure.auto_integration import validate_scaffold

router = APIRouter(prefix="/api/v1/auto-integration", tags=["auto-integration"])


class AnalyzeRequest(BaseModel):
    technology: str = Field(min_length=1)
    capabilities: list[str] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    technology: str = Field(min_length=1)
    category: str = Field(min_length=1)
    target_methods: dict[str, str] = Field(default_factory=dict)


class ValidateRequest(BaseModel):
    category: str = Field(min_length=1)
    source: str = Field(min_length=1)


def _engine(request: Request):
    engine = getattr(request.app.state, "auto_integration", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Auto-integration engine not available")
    return engine


@router.post("/analyze")
async def analyze_technology(body: AnalyzeRequest, request: Request) -> dict[str, Any]:
    try:
        return _engine(request).analyze(body.technology, body.capabilities).to_dict()
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "code": "INVALID_ANALYSIS"},
        ) from exc


@router.post("/generate")
async def generate_adapter(body: GenerateRequest, request: Request) -> dict[str, Any]:
    try:
        return _engine(request).generate(
            body.technology, body.category, body.target_methods
        ).to_dict()
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "code": "INVALID_GENERATION"},
        ) from exc


@router.post("/validate")
async def validate_adapter_source(body: ValidateRequest) -> dict[str, Any]:
    """Static validation of (possibly edited) adapter source."""
    problems = validate_scaffold(body.category, body.source)
    return {"category": body.category, "valid": not problems, "problems": problems}


@router.get("/reports")
async def list_reports(request: Request, limit: int = 20) -> dict[str, Any]:
    reports = _engine(request).list_reports(limit=limit)
    return {"reports": [r.to_dict() for r in reports], "count": len(reports)}


@router.get("/reports/{report_id}")
async def get_report(report_id: str, request: Request) -> dict[str, Any]:
    report = _engine(request).get_report(report_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Report '{report_id}' not found.", "code": "REPORT_NOT_FOUND"},
        )
    return report.to_dict()
