"""
API layer: /api/v1/qa — Autonomous QA Framework (M9.13).

Layer: Interface/Presentation.

Exposes the QAFramework: discovery from real failure signals, bug
listing/detail/close, automated reproduction through the shared
runtime, regression runs, and full QA reports.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/v1/qa", tags=["qa"])


def _qa(request: Request):
    framework = getattr(request.app.state, "qa_framework", None)
    if framework is None:
        raise HTTPException(status_code=503, detail="QA framework not available")
    return framework


@router.post("/discover")
async def discover_bugs(request: Request) -> dict[str, Any]:
    """Scan real failure signals; register new bugs."""
    bugs = _qa(request).discover()
    return {"new_bugs": [b.to_dict() for b in bugs], "count": len(bugs)}


@router.get("/bugs")
async def list_bugs(request: Request, status: str = "", source: str = "") -> dict[str, Any]:
    bugs = _qa(request).list_bugs(status=status, source=source)
    return {"bugs": [b.to_dict() for b in bugs], "count": len(bugs)}


@router.get("/bugs/{bug_id}")
async def get_bug(bug_id: str, request: Request) -> dict[str, Any]:
    bug = _qa(request).get_bug(bug_id)
    if bug is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Bug '{bug_id}' not found.", "code": "BUG_NOT_FOUND"},
        )
    return bug.to_dict()


@router.post("/bugs/{bug_id}/reproduce")
async def reproduce_bug(bug_id: str, request: Request) -> dict[str, Any]:
    """Re-execute the bug's scenario through the real runtime."""
    framework = _qa(request)
    try:
        bug = await framework.reproduce(bug_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"message": str(exc.args[0]), "code": "BUG_NOT_FOUND"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "code": "NO_REPRODUCTION_PATH"},
        ) from exc
    return bug.to_dict()


@router.post("/bugs/{bug_id}/close")
async def close_bug(bug_id: str, request: Request) -> dict[str, Any]:
    try:
        return _qa(request).close_bug(bug_id).to_dict()
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"message": str(exc.args[0]), "code": "BUG_NOT_FOUND"},
        ) from exc


@router.get("/regressions")
async def list_regressions(request: Request) -> dict[str, Any]:
    cases = _qa(request).list_regression_cases()
    return {"cases": [c.to_dict() for c in cases], "count": len(cases)}


@router.post("/regressions/run")
async def run_regressions(request: Request) -> dict[str, Any]:
    """Re-execute every stored regression case."""
    return await _qa(request).run_regressions()


@router.post("/run")
async def run_full_qa(request: Request) -> dict[str, Any]:
    """Discovery → runtime validation → regressions, one report."""
    return await _qa(request).run_full_qa()


@router.get("/reports")
async def qa_reports(request: Request, limit: int = 20) -> dict[str, Any]:
    reports = _qa(request).get_reports(limit=limit)
    return {"reports": reports, "count": len(reports)}
