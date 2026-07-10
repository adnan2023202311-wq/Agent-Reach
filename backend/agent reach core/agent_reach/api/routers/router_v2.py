"""
API layer: /api/v1/router/v2 — Smart Provider Router V2 (M10.26).

Intelligent provider selection based on cost, latency, capability,
and historical success rate. Extends the existing M7.3
ReachIntelligenceRouter with multi-factor scoring.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/router/v2", tags=["smart-router-v2"])


class ProviderScore(BaseModel):
    provider: str
    cost_score: float = 0.0      # lower cost = higher score
    latency_score: float = 0.0   # lower latency = higher score
    capability_score: float = 0.0 # more capabilities = higher score
    success_score: float = 0.0   # higher success rate = higher score
    overall_score: float = 0.0
    recommendation: str = ""  # why this provider was chosen


class RoutingDecision(BaseModel):
    request_id: str = ""
    query: str = ""
    selected_provider: str = ""
    scores: list[ProviderScore] = Field(default_factory=list)
    strategy: str = "multi_factor"
    timestamp: float = Field(default_factory=time.time)


# Provider characteristics (in production, learned from real metrics)
_PROVIDER_PROFILES = {
    "anthropic":  {"cost_per_1k": 0.015, "avg_latency_ms": 800, "capabilities": 8, "success_rate": 0.95},
    "openai":     {"cost_per_1k": 0.010, "avg_latency_ms": 600, "capabilities": 8, "success_rate": 0.93},
    "google":     {"cost_per_1k": 0.005, "avg_latency_ms": 500, "capabilities": 7, "success_rate": 0.92},
    "openrouter": {"cost_per_1k": 0.008, "avg_latency_ms": 700, "capabilities": 9, "success_rate": 0.90},
    "deepseek":   {"cost_per_1k": 0.00028, "avg_latency_ms": 1200, "capabilities": 5, "success_rate": 0.88},
    "groq":       {"cost_per_1k": 0.0002, "avg_latency_ms": 100, "capabilities": 4, "success_rate": 0.85},
}

# Configurable weights
_WEIGHTS = {"cost": 0.25, "latency": 0.25, "capability": 0.20, "success": 0.30}


def _score_provider(provider: str, profile: dict[str, Any]) -> ProviderScore:
    """Score a provider on multiple factors (each normalized to [0, 1], higher = better)."""
    max_cost = max(p["cost_per_1k"] for p in _PROVIDER_PROFILES.values())
    max_latency = max(p["avg_latency_ms"] for p in _PROVIDER_PROFILES.values())
    max_capabilities = max(p["capabilities"] for p in _PROVIDER_PROFILES.values())

    cost_score = 1.0 - (profile["cost_per_1k"] / max_cost) if max_cost > 0 else 0.5
    latency_score = 1.0 - (profile["avg_latency_ms"] / max_latency) if max_latency > 0 else 0.5
    capability_score = profile["capabilities"] / max_capabilities if max_capabilities > 0 else 0.5
    success_score = profile["success_rate"]

    overall = (
        cost_score * _WEIGHTS["cost"] +
        latency_score * _WEIGHTS["latency"] +
        capability_score * _WEIGHTS["capability"] +
        success_score * _WEIGHTS["success"]
    )

    rec_parts = []
    if cost_score > 0.7: rec_parts.append("low cost")
    if latency_score > 0.7: rec_parts.append("fast")
    if capability_score > 0.7: rec_parts.append("capable")
    if success_score > 0.9: rec_parts.append("reliable")

    return ProviderScore(
        provider=provider,
        cost_score=round(cost_score, 4),
        latency_score=round(latency_score, 4),
        capability_score=round(capability_score, 4),
        success_score=round(success_score, 4),
        overall_score=round(overall, 4),
        recommendation=", ".join(rec_parts) if rec_parts else "balanced",
    )


@router.post("/select", response_model=RoutingDecision)
async def select_provider(query: str, prefer: str = "") -> RoutingDecision:
    """Select the best provider for a query using multi-factor scoring."""
    scores = [_score_provider(p, prof) for p, prof in _PROVIDER_PROFILES.items()]
    scores.sort(key=lambda s: s.overall_score, reverse=True)

    # If user prefers a provider and it's available, use it
    selected = prefer if prefer and any(s.provider == prefer for s in scores) else scores[0].provider

    return RoutingDecision(
        query=query[:200],
        selected_provider=selected,
        scores=scores,
        strategy="multi_factor" if not prefer else "user_preference",
    )


@router.get("/scores")
async def get_all_scores() -> dict[str, Any]:
    """Get current scores for all providers."""
    scores = [_score_provider(p, prof) for p, prof in _PROVIDER_PROFILES.items()]
    scores.sort(key=lambda s: s.overall_score, reverse=True)
    return {"scores": [s.model_dump() for s in scores], "weights": _WEIGHTS}


@router.get("/weights")
async def get_weights() -> dict[str, Any]:
    """Get the current scoring weights."""
    return {"weights": _WEIGHTS, "description": "Each weight is in [0, 1] and the sum is 1.0"}


class UpdateWeightsRequest(BaseModel):
    cost: float = Field(0.25, ge=0, le=1)
    latency: float = Field(0.25, ge=0, le=1)
    capability: float = Field(0.20, ge=0, le=1)
    success: float = Field(0.30, ge=0, le=1)


@router.put("/weights")
async def update_weights(request: UpdateWeightsRequest) -> dict[str, Any]:
    """Update the scoring weights (must sum to 1.0)."""
    total = request.cost + request.latency + request.capability + request.success
    if abs(total - 1.0) > 0.01:
        return {"error": f"Weights must sum to 1.0, got {total}", "status": "rejected"}
    _WEIGHTS.update({
        "cost": request.cost, "latency": request.latency,
        "capability": request.capability, "success": request.success,
    })
    return {"weights": _WEIGHTS, "status": "updated"}


@router.get("/profiles")
async def provider_profiles() -> dict[str, Any]:
    """Get the raw provider profiles used for scoring."""
    return {"profiles": _PROVIDER_PROFILES, "count": len(_PROVIDER_PROFILES)}


@router.post("/learn")
async def record_outcome(provider: str, succeeded: bool, latency_ms: float, cost: float = 0) -> dict[str, Any]:
    """Record a real execution outcome to update the provider's profile (online learning)."""
    if provider not in _PROVIDER_PROFILES:
        return {"error": f"Unknown provider: {provider}", "status": "rejected"}
    profile = _PROVIDER_PROFILES[provider]
    # Exponential moving average for latency and success rate
    alpha = 0.1
    profile["avg_latency_ms"] = (profile["avg_latency_ms"] * (1 - alpha)) + (latency_ms * alpha)
    total = 100  # assume 100 past observations
    profile["success_rate"] = ((profile["success_rate"] * total) + (1.0 if succeeded else 0.0)) / (total + 1)
    return {"provider": provider, "updated_profile": profile, "status": "learned"}
