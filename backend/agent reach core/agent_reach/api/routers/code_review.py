"""
API layer: /api/v1/code-review — AI Code Review System (M9.15).

Layer: Interface/Presentation.

Exposes the CodeReviewEngine: deterministic static review (verdict
authority), optional model narrative through the shared pipeline
(advisory, trace-linked), review history, and stats.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/code-review", tags=["code-review"])


class ReviewRequest(BaseModel):
    source: str = Field(min_length=1)
    file_path: str = ""
    include_model_review: bool = False


def _engine(request: Request):
    engine = getattr(request.app.state, "code_review", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Code review engine not available")
    return engine


@router.post("")
async def review_code(body: ReviewRequest, request: Request) -> dict[str, Any]:
    """Review a code change. Verdict derives from static findings."""
    engine = _engine(request)
    if body.include_model_review:
        result = await engine.review_with_model(body.source, file_path=body.file_path)
    else:
        result = engine.review(body.source, file_path=body.file_path)
    return result.to_dict()


@router.get("/reviews")
async def list_reviews(request: Request, limit: int = 20) -> dict[str, Any]:
    reviews = _engine(request).list_reviews(limit=limit)
    return {"reviews": [r.to_dict() for r in reviews], "count": len(reviews)}


@router.get("/reviews/{review_id}")
async def get_review(review_id: str, request: Request) -> dict[str, Any]:
    review = _engine(request).get_review(review_id)
    if review is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Review '{review_id}' not found.", "code": "REVIEW_NOT_FOUND"},
        )
    return review.to_dict()


@router.get("/stats")
async def review_stats(request: Request) -> dict[str, Any]:
    return _engine(request).get_stats()
