"""
API layer: /api/v1/evolution — Continuous Evolution Platform (M10.24).

Every subsystem remains upgradeable independently through plugins and
adapters without breaking existing deployments. Manages versioned
upgrades, migration paths, compatibility matrices, and rolling updates.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/evolution", tags=["continuous-evolution"])


class SubsystemVersion(BaseModel):
    subsystem: str
    current_version: str
    available_version: str = ""
    upgrade_available: bool = False
    compatibility: str = "compatible"  # compatible | requires_migration | breaking
    migration_path: list[str] = Field(default_factory=list)


class UpgradeJob(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    subsystem: str
    from_version: str
    to_version: str
    status: str = "pending"  # pending | in_progress | completed | failed | rolled_back
    started_at: float = Field(default_factory=time.time)
    completed_at: float = 0.0
    rollback_available: bool = True


_subsystems: dict[str, SubsystemVersion] = {
    "core": SubsystemVersion(subsystem="core", current_version="10.0.0"),
    "providers": SubsystemVersion(subsystem="providers", current_version="10.0.0"),
    "agents": SubsystemVersion(subsystem="agents", current_version="10.0.0"),
    "memory": SubsystemVersion(subsystem="memory", current_version="10.0.0"),
    "knowledge": SubsystemVersion(subsystem="knowledge", current_version="10.0.0"),
    "workflows": SubsystemVersion(subsystem="workflows", current_version="10.0.0"),
    "marketplace": SubsystemVersion(subsystem="marketplace", current_version="10.0.0"),
    "security": SubsystemVersion(subsystem="security", current_version="10.0.0"),
    "distributed": SubsystemVersion(subsystem="distributed", current_version="10.0.0"),
    "enterprise": SubsystemVersion(subsystem="enterprise", current_version="10.0.0"),
}
_upgrade_jobs: dict[str, UpgradeJob] = {}


@router.get("/subsystems")
async def list_subsystems() -> dict[str, Any]:
    """List all subsystems and their version status."""
    return {"subsystems": [s.model_dump() for s in _subsystems.values()], "count": len(_subsystems)}


@router.get("/subsystems/{name}")
async def get_subsystem(name: str) -> dict[str, Any]:
    if name not in _subsystems:
        raise HTTPException(status_code=404, detail=f"Subsystem '{name}' not found")
    return _subsystems[name].model_dump()


class CheckUpgradeRequest(BaseModel):
    subsystem: str
    target_version: str


@router.post("/check-upgrade")
async def check_upgrade(request: CheckUpgradeRequest) -> dict[str, Any]:
    """Check if an upgrade is compatible and what migration is needed."""
    subsystem = _subsystems.get(request.subsystem)
    if subsystem is None:
        raise HTTPException(status_code=404, detail="Subsystem not found")
    # Simple semver comparison
    def parse(v: str) -> tuple[int, int, int]:
        try:
            parts = v.split(".")
            return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0, int(parts[2]) if len(parts) > 2 else 0)
        except (ValueError, IndexError):
            return (0, 0, 0)

    current = parse(subsystem.current_version)
    target = parse(request.target_version)
    if target > current:
        subsystem.available_version = request.target_version
        subsystem.upgrade_available = True
        # Major version bump = potential breaking change
        if target[0] > current[0]:
            subsystem.compatibility = "breaking"
            subsystem.migration_path = [
                f"Backup {request.subsystem} data",
                f"Run migration script for v{current[0]} → v{target[0]}",
                f"Update {request.subsystem} configuration",
                f"Verify {request.subsystem} functionality",
            ]
        elif target[1] > current[1]:
            subsystem.compatibility = "requires_migration"
            subsystem.migration_path = [f"Run minor migration for {request.subsystem}"]
        else:
            subsystem.compatibility = "compatible"
            subsystem.migration_path = []
    return {
        "subsystem": request.subsystem,
        "current_version": subsystem.current_version,
        "target_version": request.target_version,
        "compatible": subsystem.compatibility != "breaking",
        "migration_required": subsystem.compatibility != "compatible",
        "migration_path": subsystem.migration_path,
    }


@router.post("/upgrade")
async def execute_upgrade(subsystem: str, target_version: str) -> dict[str, Any]:
    """Execute a subsystem upgrade."""
    sub = _subsystems.get(subsystem)
    if sub is None:
        raise HTTPException(status_code=404, detail="Subsystem not found")
    job = UpgradeJob(
        subsystem=subsystem, from_version=sub.current_version, to_version=target_version,
        status="completed", completed_at=time.time(),
    )
    _upgrade_jobs[job.job_id] = job
    sub.current_version = target_version
    sub.upgrade_available = False
    sub.available_version = ""
    return {"job_id": job.job_id, "subsystem": subsystem, "status": "completed", "new_version": target_version}


@router.post("/upgrade/{job_id}/rollback")
async def rollback_upgrade(job_id: str) -> dict[str, Any]:
    """Rollback a completed upgrade."""
    job = _upgrade_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Upgrade job not found")
    if not job.rollback_available:
        raise HTTPException(status_code=400, detail="Rollback not available")
    job.status = "rolled_back"
    sub = _subsystems.get(job.subsystem)
    if sub:
        sub.current_version = job.from_version
    return {"job_id": job_id, "status": "rolled_back", "reverted_to": job.from_version}


@router.get("/jobs")
async def list_upgrade_jobs(limit: int = 20) -> dict[str, Any]:
    jobs = sorted(_upgrade_jobs.values(), key=lambda j: j.started_at, reverse=True)
    return {"jobs": [j.model_dump() for j in jobs[:limit]], "count": len(jobs)}


@router.get("/compatibility-matrix")
async def compatibility_matrix() -> dict[str, Any]:
    """Show version compatibility between all subsystems."""
    return {
        "matrix": {
            name: {
                "version": s.current_version,
                "compatible_with": {n: o.current_version for n, o in _subsystems.items() if n != name},
            }
            for name, s in _subsystems.items()
        },
        "policy": "Minor and patch versions are always compatible. Major version changes require migration.",
    }
