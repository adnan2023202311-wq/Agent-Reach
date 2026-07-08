"""
API layer: /api/v1/platform — Self-Developing Platform (M9.11).

Layer: Interface/Presentation.

Exposes PlatformIntrospection: full self-description, weakness/
bottleneck findings with evidence, live smoke validation, and the
improve endpoint that measures a real before/after around the M9.14
safe-apply path (the single application mechanism — no duplicate).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])


def _introspection(request: Request):
    engine = getattr(request.app.state, "platform_introspection", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Platform introspection not available")
    return engine


@router.get("/inspect")
async def inspect_platform(request: Request) -> dict[str, Any]:
    """Full self-description from live sources."""
    return _introspection(request).inspect()


@router.get("/analyze")
async def analyze_platform(request: Request) -> dict[str, Any]:
    """Weakness/bottleneck findings. Healthy idle platform → empty."""
    findings = _introspection(request).analyze()
    return {
        "findings": [f.to_dict() for f in findings],
        "count": len(findings),
        "by_severity": {
            severity: sum(1 for f in findings if f.severity == severity)
            for severity in ("critical", "warning", "info")
        },
    }


@router.post("/validate")
async def validate_platform(request: Request) -> dict[str, Any]:
    """Live smoke validation: subsystems + one real pipeline run."""
    return await _introspection(request).validate()


@router.post("/improve")
async def improve_platform(request: Request) -> dict[str, Any]:
    """Measure → apply safe optimizations (M9.14 path) → measure.

    The report contains the real before/after runtime aggregates and
    exactly what was applied vs. skipped.
    """
    introspection = _introspection(request)
    optimization = getattr(request.app.state, "optimization_engine", None)
    if optimization is None:
        raise HTTPException(status_code=503, detail="Optimization engine not available")

    before = introspection.inspect()
    report = optimization.apply()
    after = introspection.inspect()
    return {
        "before": {"runtime": before["runtime"], "subsystems_active": before["subsystems"]["active_count"]},
        "optimization_report": report,
        "after": {"runtime": after["runtime"], "subsystems_active": after["subsystems"]["active_count"]},
    }
