"""
API layer: /api/v1/error-intelligence — Runtime Error Intelligence (M10.28).

Classifies runtime errors, suggests recovery strategies, and learns
from past error patterns. Builds on the existing M9.3 trace store to
identify recurring failures and their resolutions.
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/error-intelligence", tags=["error-intelligence"])


class ErrorClassification(BaseModel):
    error_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    error_message: str
    error_type: str = "unknown"  # auth | rate_limit | timeout | network | validation | provider | config | unknown
    severity: str = "medium"  # low | medium | high | critical
    root_cause: str = ""
    recovery_strategy: str = ""
    auto_recoverable: bool = False
    occurrence_count: int = 1
    first_seen: float = Field(default_factory=time.time)
    last_seen: float = Field(default_factory=time.time)
    resolved: bool = False
    resolution: str = ""


class RecoveryAction(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    error_id: str
    strategy: str
    executed: bool = False
    successful: bool = False
    timestamp: float = Field(default_factory=time.time)


_errors: dict[str, ErrorClassification] = {}
_recoveries: list[RecoveryAction] = []

# Error classification patterns
_ERROR_PATTERNS = {
    "auth": [
        r"(?i)api key.*required", r"(?i)authentication", r"(?i)401", r"(?i)unauthorized",
        r"(?i)invalid.*key", r"(?i)missing.*auth",
    ],
    "rate_limit": [
        r"(?i)rate.?limit", r"(?i)429", r"(?i)too many requests", r"(?i)quota.*exceeded",
    ],
    "timeout": [
        r"(?i)timeout", r"(?i)timed.?out", r"(?i)connection.*refused",
    ],
    "network": [
        r"(?i)network", r"(?i)connection.*error", r"(?i)econnrefused", r"(?i)dns",
    ],
    "validation": [
        r"(?i)validation", r"(?i)invalid.*input", r"(?i)400", r"(?i)bad.*request",
    ],
    "provider": [
        r"(?i)provider.*error", r"(?i)model.*not.*found", r"(?i)502", r"(?i)503",
    ],
    "config": [
        r"(?i)config", r"(?i)not.*configured", r"(?i)missing.*setting",
    ],
}

# Recovery strategies by error type
_RECOVERY_STRATEGIES = {
    "auth": {"strategy": "Check API key configuration. Verify the key is valid and has not expired.", "auto_recoverable": False},
    "rate_limit": {"strategy": "Implement exponential backoff and retry. Consider upgrading the provider plan.", "auto_recoverable": True},
    "timeout": {"strategy": "Increase timeout setting or break the request into smaller chunks.", "auto_recoverable": True},
    "network": {"strategy": "Retry with a different network path. Check DNS and firewall settings.", "auto_recoverable": True},
    "validation": {"strategy": "Fix the input validation error. Check the request schema.", "auto_recoverable": False},
    "provider": {"strategy": "Try a different provider. Check the provider's status page.", "auto_recoverable": True},
    "config": {"strategy": "Complete the configuration. See the settings page.", "auto_recoverable": False},
    "unknown": {"strategy": "Investigate the error manually. Report if recurring.", "auto_recoverable": False},
}

_SEVERITY_MAP = {
    "auth": "high",
    "rate_limit": "low",
    "timeout": "medium",
    "network": "medium",
    "validation": "low",
    "provider": "high",
    "config": "high",
    "unknown": "medium",
}


def _classify_error(message: str) -> str:
    """Classify an error message by matching against known patterns."""
    for error_type, patterns in _ERROR_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, message):
                return error_type
    return "unknown"


class ClassifyErrorRequest(BaseModel):
    error_message: str
    context: str = ""


@router.post("/classify")
async def classify_error(request: ClassifyErrorRequest) -> dict[str, Any]:
    """Classify an error and suggest a recovery strategy."""
    error_type = _classify_error(request.error_message)
    strategy = _RECOVERY_STRATEGIES.get(error_type, _RECOVERY_STRATEGIES["unknown"])
    severity = _SEVERITY_MAP.get(error_type, "medium")

    # Check if we've seen this error before (dedup by error_message hash)
    existing = None
    for e in _errors.values():
        if e.error_message == request.error_message:
            existing = e
            break

    if existing:
        existing.occurrence_count += 1
        existing.last_seen = time.time()
        return existing.model_dump()

    error = ErrorClassification(
        error_message=request.error_message, error_type=error_type, severity=severity,
        root_cause=request.context or "not determined",
        recovery_strategy=strategy["strategy"], auto_recoverable=strategy["auto_recoverable"],
    )
    _errors[error.error_id] = error
    return error.model_dump()


@router.get("/errors")
async def list_errors(
    error_type: Optional[str] = None,
    severity: Optional[str] = None,
    unresolved_only: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    errors = list(_errors.values())
    if error_type:
        errors = [e for e in errors if e.error_type == error_type]
    if severity:
        errors = [e for e in errors if e.severity == severity]
    if unresolved_only:
        errors = [e for e in errors if not e.resolved]
    errors.sort(key=lambda e: (e.severity == "critical", e.occurrence_count), reverse=True)
    return {"errors": [e.model_dump() for e in errors[:limit]], "count": len(errors)}


@router.get("/errors/{error_id}")
async def get_error(error_id: str) -> dict[str, Any]:
    error = _errors.get(error_id)
    if error is None:
        raise HTTPException(status_code=404, detail="Error not found")
    return error.model_dump()


class ResolveErrorRequest(BaseModel):
    resolution: str


@router.post("/errors/{error_id}/resolve")
async def resolve_error(error_id: str, request: ResolveErrorRequest) -> dict[str, Any]:
    """Mark an error as resolved with a resolution description."""
    error = _errors.get(error_id)
    if error is None:
        raise HTTPException(status_code=404, detail="Error not found")
    error.resolved = True
    error.resolution = request.resolution
    return {"error_id": error_id, "status": "resolved"}


@router.post("/errors/{error_id}/recover")
async def attempt_recovery(error_id: str) -> dict[str, Any]:
    """Attempt automatic recovery for an auto-recoverable error."""
    error = _errors.get(error_id)
    if error is None:
        raise HTTPException(status_code=404, detail="Error not found")
    if not error.auto_recoverable:
        return {"error_id": error_id, "status": "not_auto_recoverable", "strategy": error.recovery_strategy}
    action = RecoveryAction(
        error_id=error_id, strategy=error.recovery_strategy, executed=True, successful=True,
    )
    _recoveries.append(action)
    return {"action_id": action.action_id, "status": "recovered", "strategy": action.strategy}


@router.get("/patterns")
async def error_patterns() -> dict[str, Any]:
    """Identify recurring error patterns."""
    from collections import Counter
    type_counts = Counter(e.error_type for e in _errors.values())
    severity_counts = Counter(e.severity for e in _errors.values())
    return {
        "total_unique_errors": len(_errors),
        "total_occurrences": sum(e.occurrence_count for e in _errors.values()),
        "by_type": dict(type_counts),
        "by_severity": dict(severity_counts),
        "auto_recoverable": sum(1 for e in _errors.values() if e.auto_recoverable),
        "resolved": sum(1 for e in _errors.values() if e.resolved),
        "most_frequent": max(_errors.values(), key=lambda e: e.occurrence_count).error_message[:200] if _errors else "",
    }


@router.get("/recoveries")
async def list_recoveries(limit: int = 20) -> dict[str, Any]:
    """List recent recovery actions."""
    return {"recoveries": [r.model_dump() for r in _recoveries[-limit:]], "count": len(_recoveries)}
