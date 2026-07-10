"""
API layer: /api/v1/billing — Billing & Resource Management (M10.15).

Usage tracking, credits, billing, quotas, and cost optimization.
Tracks API calls, token usage, and estimated costs per organization/user.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


class UsageRecord(BaseModel):
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str = ""
    user_id: str = ""
    provider: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    timestamp: float = Field(default_factory=time.time)


class CreditBalance(BaseModel):
    org_id: str
    credits: float = 0.0
    free_tier_limit: float = 100.0
    used_this_period: float = 0.0
    period_start: float = Field(default_factory=time.time)


class Quota(BaseModel):
    org_id: str
    requests_per_minute: int = 60
    requests_per_day: int = 10000
    tokens_per_day: int = 1000000
    current_rpm: int = 0
    current_daily_requests: int = 0
    current_daily_tokens: int = 0


_usage: list[UsageRecord] = []
_credits: dict[str, CreditBalance] = {}
_quotas: dict[str, Quota] = {}

# Provider cost per 1K tokens (estimated)
PROVIDER_COSTS = {
    "anthropic": {"in": 0.003, "out": 0.015},
    "openai": {"in": 0.0025, "out": 0.01},
    "google": {"in": 0.00125, "out": 0.005},
    "openrouter": {"in": 0.002, "out": 0.008},
    "deepseek": {"in": 0.00014, "out": 0.00028},
    "groq": {"in": 0.0001, "out": 0.0002},
}


class RecordUsageRequest(BaseModel):
    org_id: str = ""
    user_id: str = ""
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0


@router.post("/usage")
async def record_usage(request: RecordUsageRequest) -> dict[str, Any]:
    """Record a usage event (called after each API call)."""
    costs = PROVIDER_COSTS.get(request.provider, {"in": 0.001, "out": 0.002})
    cost = (request.tokens_in / 1000.0 * costs["in"]) + (request.tokens_out / 1000.0 * costs["out"])
    record = UsageRecord(
        org_id=request.org_id, user_id=request.user_id, provider=request.provider,
        tokens_in=request.tokens_in, tokens_out=request.tokens_out, cost=cost,
    )
    _usage.append(record)
    if len(_usage) > 10000:
        _usage[:] = _usage[-5000:]
    # Update credits
    if request.org_id:
        credit = _credits.setdefault(request.org_id, CreditBalance(org_id=request.org_id))
        credit.used_this_period += cost
        credit.credits -= cost
    return {"record_id": record.record_id, "cost": round(cost, 6), "status": "recorded"}


@router.get("/usage")
async def get_usage(
    org_id: Optional[str] = None,
    provider: Optional[str] = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Query usage records."""
    records = list(_usage)
    if org_id:
        records = [r for r in records if r.org_id == org_id]
    if provider:
        records = [r for r in records if r.provider == provider]
    return {
        "usage": [r.model_dump() for r in records[-limit:]],
        "count": len(records),
    }


@router.get("/usage/summary")
async def usage_summary(org_id: Optional[str] = None) -> dict[str, Any]:
    """Aggregate usage statistics."""
    records = [r for r in _usage if not org_id or r.org_id == org_id]
    total_cost = sum(r.cost for r in records)
    total_tokens_in = sum(r.tokens_in for r in records)
    total_tokens_out = sum(r.tokens_out for r in records)
    by_provider: dict[str, dict[str, float]] = {}
    for r in records:
        p = r.provider
        if p not in by_provider:
            by_provider[p] = {"requests": 0, "cost": 0.0, "tokens_in": 0, "tokens_out": 0}
        by_provider[p]["requests"] += 1
        by_provider[p]["cost"] += r.cost
        by_provider[p]["tokens_in"] += r.tokens_in
        by_provider[p]["tokens_out"] += r.tokens_out
    return {
        "total_requests": len(records),
        "total_cost": round(total_cost, 4),
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "by_provider": {k: {**v, "cost": round(v["cost"], 4)} for k, v in by_provider.items()},
    }


@router.get("/credits/{org_id}")
async def get_credits(org_id: str) -> dict[str, Any]:
    """Get credit balance for an organization."""
    credit = _credits.get(org_id, CreditBalance(org_id=org_id))
    return credit.model_dump()


@router.post("/credits/{org_id}")
async def add_credits(org_id: str, amount: float) -> dict[str, Any]:
    """Add credits to an organization."""
    credit = _credits.setdefault(org_id, CreditBalance(org_id=org_id))
    credit.credits += amount
    return {"org_id": org_id, "credits": credit.credits, "added": amount}


@router.get("/quotas/{org_id}")
async def get_quota(org_id: str) -> dict[str, Any]:
    """Get quota limits for an organization."""
    quota = _quotas.get(org_id, Quota(org_id=org_id))
    return quota.model_dump()


@router.put("/quotas/{org_id}")
async def set_quota(org_id: str, requests_per_minute: int, requests_per_day: int, tokens_per_day: int) -> dict[str, Any]:
    """Set quota limits for an organization."""
    quota = _quotas.setdefault(org_id, Quota(org_id=org_id))
    quota.requests_per_minute = requests_per_minute
    quota.requests_per_day = requests_per_day
    quota.tokens_per_day = tokens_per_day
    return {"status": "updated", "quota": quota.model_dump()}


@router.get("/cost-optimization")
async def cost_optimization() -> dict[str, Any]:
    """Suggest cost optimizations based on usage patterns."""
    records = list(_usage)
    if not records:
        return {"suggestions": [], "status": "no_data"}
    suggestions: list[dict[str, Any]] = []
    # Find the most expensive provider
    by_cost: dict[str, float] = {}
    for r in records:
        by_cost[r.provider] = by_cost.get(r.provider, 0.0) + r.cost
    if by_cost:
        most_expensive = max(by_cost, key=by_cost.get)
        cheapest = min(by_cost, key=by_cost.get) if len(by_cost) > 1 else None
        if cheapest and by_cost[most_expensive] > by_cost[cheapest] * 2:
            suggestions.append({
                "type": "provider_switch",
                "description": f"Switching from {most_expensive} to {cheapest} could save ~${round(by_cost[most_expensive] - by_cost[cheapest], 2)}/period",
                "potential_savings": round(by_cost[most_expensive] - by_cost[cheapest], 4),
            })
    # Suggest caching for repeated queries
    if len(records) > 100:
        suggestions.append({
            "type": "caching",
            "description": "Enable response caching for repeated queries to reduce API calls.",
            "potential_savings": round(sum(r.cost for r in records) * 0.15, 4),
        })
    return {"suggestions": suggestions, "status": "analyzed"}
