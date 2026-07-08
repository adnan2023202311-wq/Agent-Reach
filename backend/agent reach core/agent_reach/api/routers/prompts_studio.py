"""
API layer: /api/v1/prompts — Prompt Studio (M9.20).

Layer: Interface/Presentation.

M9.20 replaces the M8 version — which probed for methods the
PromptLibrary never had (`add`, `list`, `history`), fell back to a
module-level dict, and served a hardcoded "optimize" stub with an
invented '+12%' score — with the real PromptEvolutionEngine
(prompts/evolution.py) composed over the M7 PromptIntelligence and
PromptLibrary, held on app.state.

Endpoints keep the M8 shapes the frontend uses (list/create/get/test)
and add the M9.20 evolution surface: analysis, evidence-based
proposals, apply, version history, and rollback.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/prompts", tags=["prompts"])


class PromptCreate(BaseModel):
    name: str = Field(min_length=1)
    template: str = Field(min_length=1)
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class PromptTestRequest(BaseModel):
    template: str
    variables: dict[str, Any] = Field(default_factory=dict)


class PromptUsageRecord(BaseModel):
    output_quality: float = Field(ge=0.0, le=1.0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    provider: str = ""
    variables: dict[str, Any] = Field(default_factory=dict)


class ExternalProposal(BaseModel):
    proposed_template: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence: dict[str, Any] = Field(default_factory=dict)


class RollbackRequest(BaseModel):
    version: int = Field(ge=1)


def _evolution(request: Request):
    engine = getattr(request.app.state, "prompt_evolution", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Prompt evolution engine not available")
    return engine


def _require_prompt(engine, name: str):
    prompt = engine.library.get(name)
    if prompt is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Prompt '{name}' not found.", "code": "PROMPT_NOT_FOUND"},
        )
    return prompt


@router.get("")
async def list_prompts(request: Request, search: str = "", tag: str = "") -> dict[str, Any]:
    engine = _evolution(request)
    if search:
        prompts = engine.library.search(search)
    elif tag:
        prompts = engine.library.list_prompts(tag=tag)
    else:
        prompts = engine.library.list_prompts()
    return {"items": [p.to_dict() for p in prompts], "count": len(prompts)}


@router.post("")
async def create_prompt(p: PromptCreate, request: Request) -> dict[str, Any]:
    engine = _evolution(request)
    prompt = engine.library.register(
        p.name, p.template, description=p.description, tags=p.tags
    )
    return {"name": prompt.name, "version": prompt.version, "status": "created"}


@router.post("/test")
async def test_prompt(req: PromptTestRequest, request: Request) -> dict[str, Any]:
    """Render a template with variables — fast preview, no LLM call.

    Uses the library's real renderer on a transient template.
    """
    engine = _evolution(request)
    # Render through the library's engine on a scratch registration,
    # then remove it — same renderer, no divergent logic.
    scratch = "__scratch_preview__"
    engine.library.register(scratch, req.template)
    try:
        rendered = engine.library.render(scratch, req.variables)
    finally:
        engine.library.unregister(scratch)
    return {
        "rendered": rendered,
        "tokens_estimate": len(rendered) // 4,
        "variables_used": list(req.variables.keys()),
        "length": len(rendered),
    }


@router.get("/{name}")
async def get_prompt(name: str, request: Request) -> dict[str, Any]:
    engine = _evolution(request)
    prompt = _require_prompt(engine, name)
    return prompt.to_dict()


@router.post("/{name}/usage")
async def record_usage(name: str, body: PromptUsageRecord, request: Request) -> dict[str, Any]:
    """Record real usage feedback — the evidence evolution runs on."""
    engine = _evolution(request)
    _require_prompt(engine, name)
    engine.intelligence.record_usage(
        name,
        variables=body.variables,
        output_quality=body.output_quality,
        latency_ms=body.latency_ms,
        provider=body.provider,
    )
    return {"name": name, "status": "recorded",
            "learning": engine.intelligence.get_learning_stats(name)}


@router.get("/{name}/analysis")
async def analyze_prompt(name: str, request: Request) -> dict[str, Any]:
    """Real usage + structural analysis (M9.20)."""
    engine = _evolution(request)
    _require_prompt(engine, name)
    return engine.analyze(name)


@router.post("/{name}/optimize")
async def optimize_prompt(name: str, request: Request) -> dict[str, Any]:
    """Generate evidence-based evolution proposals (M9.20).

    Replaces the M8 stub that returned hardcoded suggestions and an
    invented '+12%' improvement. No usage data → honest emptiness.
    """
    engine = _evolution(request)
    _require_prompt(engine, name)
    proposals = engine.propose(name)
    return {
        "name": name,
        "proposals": [p.to_dict() for p in proposals],
        "count": len(proposals),
        "structural_suggestions": engine.intelligence.suggest_optimizations(name),
    }


@router.post("/{name}/proposals")
async def register_external_proposal(
    name: str, body: ExternalProposal, request: Request
) -> dict[str, Any]:
    """Register an externally generated improvement proposal."""
    engine = _evolution(request)
    _require_prompt(engine, name)
    proposal = engine.propose_external(
        name, body.proposed_template, rationale=body.rationale, evidence=body.evidence
    )
    return proposal.to_dict()


@router.post("/proposals/{proposal_id}/apply")
async def apply_proposal(proposal_id: str, request: Request) -> dict[str, Any]:
    """Apply a proposal — snapshots the prior version for rollback."""
    engine = _evolution(request)
    try:
        return engine.apply_proposal(proposal_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"message": str(exc), "code": "PROPOSAL_NOT_FOUND"},
        ) from exc


@router.get("/{name}/history")
async def prompt_history(name: str, request: Request) -> dict[str, Any]:
    """Recorded version snapshots, oldest first (M9.20)."""
    engine = _evolution(request)
    prompt = _require_prompt(engine, name)
    snapshots = engine.get_history(name)
    return {
        "name": name,
        "current_version": prompt.version,
        "versions": [s.to_dict() for s in snapshots],
        "count": len(snapshots),
    }


@router.post("/{name}/rollback")
async def rollback_prompt(name: str, body: RollbackRequest, request: Request) -> dict[str, Any]:
    """Restore a recorded version as a NEW version (M9.20)."""
    engine = _evolution(request)
    _require_prompt(engine, name)
    try:
        return engine.rollback(name, body.version)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"message": str(exc), "code": "VERSION_NOT_FOUND"},
        ) from exc
