"""
Agents layer: Global Agent Registry (M10.3 — Global Agent Registry).

Layer: Adapters — extends the existing M6.5 AgentRegistry with global
discovery, trust scoring, versioning, and compatibility checks.

This module does NOT replace agents/agent_registry.py. It wraps it,
adding the M10.3 global discovery surface on top. The existing
AgentRegistry continues to handle local agent registration and
dependency validation; this layer adds:

- **Discovery**: search agents by name, tag, category, capability
- **Versioning**: track multiple versions of the same agent; resolve
  "latest compatible" for a given platform version
- **Trust score**: 0.0–1.0 based on success rate, execution count,
  and community feedback
- **Compatibility**: semver check against the platform version
- **Verification**: mark agents as verified (manually or by automated
  QA) so consumers can filter to trusted-only

The registry is in-memory. For a true global registry (cross-cluster),
swap this for a Redis-backed implementation — the interface is stable.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentTrustScore:
    """Trust metrics for a globally-registered agent.

    The score is a weighted blend of:
    - success_rate (50%): successful_executions / total_executions
    - adoption (30%): min(total_executions / 100, 1.0)
    - verification (20%): 1.0 if verified, 0.0 otherwise
    """

    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    avg_latency_ms: float = 0.0
    community_rating: float = 0.0  # 0.0–5.0 (star rating)
    rating_count: int = 0
    verified: bool = False

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions

    @property
    def score(self) -> float:
        """Composite trust score in [0.0, 1.0]."""
        adoption = min(self.total_executions / 100.0, 1.0)
        verification = 1.0 if self.verified else 0.0
        return (self.success_rate * 0.5) + (adoption * 0.3) + (verification * 0.2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "success_rate": round(self.success_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "community_rating": self.community_rating,
            "rating_count": self.rating_count,
            "verified": self.verified,
            "score": round(self.score, 4),
        }


@dataclass
class GlobalAgentEntry:
    """One agent in the global registry.

    An agent is identified by (agent_id, version). Multiple versions
    of the same agent_id can coexist; consumers request "latest
    compatible" or a specific version.
    """

    agent_id: str
    name: str
    version: str  # semver, e.g. "1.2.0"
    description: str = ""
    author: str = ""
    homepage: str = ""
    category: str = "general"  # research, coding, browser, writing, etc.
    tags: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)  # agent types
    dependencies: list[str] = field(default_factory=list)  # e.g. ["providers:openai"]
    min_platform_version: str = "0.0.0"
    trust: AgentTrustScore = field(default_factory=AgentTrustScore)
    registered_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "homepage": self.homepage,
            "category": self.category,
            "tags": list(self.tags),
            "capabilities": list(self.capabilities),
            "dependencies": list(self.dependencies),
            "min_platform_version": self.min_platform_version,
            "trust": self.trust.to_dict(),
            "registered_at": self.registered_at,
            "metadata": dict(self.metadata),
        }


def _parse_semver(v: str) -> tuple[int, int, int]:
    """Parse a semver string into (major, minor, patch). Returns (0,0,0) on error."""
    try:
        parts = v.strip().split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return (major, minor, patch)
    except (ValueError, IndexError):
        return (0, 0, 0)


class GlobalAgentRegistry:
    """In-memory global registry of discoverable agents.

    Keyed by (agent_id, version). Supports:
    - register(entry) — add or update an agent version
    - discover(query, category, tag, capability, min_trust) — search
    - get_latest(agent_id, platform_version) — resolve latest compatible
    - record_execution(agent_id, version, succeeded, latency_ms) — update trust
    - rate(agent_id, version, stars) — community rating
    - verify(agent_id, version) — mark as verified
    """

    def __init__(self, platform_version: str = "10.0.0") -> None:
        self._platform_version = platform_version
        self._entries: dict[tuple[str, str], GlobalAgentEntry] = {}

    @property
    def platform_version(self) -> str:
        return self._platform_version

    def register(self, entry: GlobalAgentEntry) -> None:
        """Add or update an agent version."""
        key = (entry.agent_id, entry.version)
        self._entries[key] = entry
        logger.info(
            "GlobalAgentRegistry: registered %s v%s (category=%s, trust=%.2f)",
            entry.agent_id, entry.version, entry.category, entry.trust.score,
        )

    def unregister(self, agent_id: str, version: str) -> bool:
        key = (agent_id, version)
        existed = self._entries.pop(key, None) is not None
        if existed:
            logger.info("GlobalAgentRegistry: unregistered %s v%s", agent_id, version)
        return existed

    def get(self, agent_id: str, version: str) -> Optional[GlobalAgentEntry]:
        return self._entries.get((agent_id, version))

    def get_latest(
        self,
        agent_id: str,
        platform_version: Optional[str] = None,
    ) -> Optional[GlobalAgentEntry]:
        """Return the highest-version entry for agent_id that's compatible.

        Compatibility is checked against platform_version (defaults to
        this registry's platform_version). Returns None if no compatible
        version exists.
        """
        pv = _parse_semver(platform_version or self._platform_version)
        candidates = [
            e for e in self._entries.values()
            if e.agent_id == agent_id and _parse_semver(e.min_platform_version) <= pv
        ]
        if not candidates:
            return None
        # Sort by semver descending.
        candidates.sort(key=lambda e: _parse_semver(e.version), reverse=True)
        return candidates[0]

    def discover(
        self,
        query: str = "",
        category: Optional[str] = None,
        tag: Optional[str] = None,
        capability: Optional[str] = None,
        min_trust: float = 0.0,
        verified_only: bool = False,
        limit: int = 50,
    ) -> list[GlobalAgentEntry]:
        """Search the registry. Returns entries sorted by trust score."""
        query_lower = query.lower().strip()
        results: list[GlobalAgentEntry] = []
        for entry in self._entries.values():
            if category and entry.category != category:
                continue
            if tag and tag not in entry.tags:
                continue
            if capability and capability not in entry.capabilities:
                continue
            if entry.trust.score < min_trust:
                continue
            if verified_only and not entry.trust.verified:
                continue
            if query_lower:
                haystack = f"{entry.name} {entry.description} {' '.join(entry.tags)}".lower()
                if query_lower not in haystack:
                    continue
            results.append(entry)
        results.sort(key=lambda e: e.trust.score, reverse=True)
        return results[:limit]

    def record_execution(
        self,
        agent_id: str,
        version: str,
        succeeded: bool,
        latency_ms: float,
    ) -> None:
        """Update an agent's trust metrics after an execution."""
        entry = self._entries.get((agent_id, version))
        if entry is None:
            return
        t = entry.trust
        # Running average for latency.
        t.total_executions += 1
        t.avg_latency_ms = ((t.avg_latency_ms * (t.total_executions - 1)) + latency_ms) / t.total_executions
        if succeeded:
            t.successful_executions += 1
        else:
            t.failed_executions += 1

    def rate(self, agent_id: str, version: str, stars: float) -> None:
        """Add a community rating (0.0–5.0 stars)."""
        entry = self._entries.get((agent_id, version))
        if entry is None:
            return
        t = entry.trust
        stars = max(0.0, min(5.0, stars))
        # Running average.
        total = t.community_rating * t.rating_count + stars
        t.rating_count += 1
        t.community_rating = total / t.rating_count

    def verify(self, agent_id: str, version: str) -> bool:
        """Mark an agent version as verified. Returns False if not found."""
        entry = self._entries.get((agent_id, version))
        if entry is None:
            return False
        entry.trust.verified = True
        logger.info("GlobalAgentRegistry: verified %s v%s", agent_id, version)
        return True

    def list_categories(self) -> list[str]:
        """All unique categories in the registry."""
        return sorted({e.category for e in self._entries.values()})

    def stats(self) -> dict[str, Any]:
        """Aggregate registry stats for the monitoring center."""
        total = len(self._entries)
        verified = sum(1 for e in self._entries.values() if e.trust.verified)
        avg_trust = sum(e.trust.score for e in self._entries.values()) / max(1, total)
        return {
            "total_agents": total,
            "verified": verified,
            "avg_trust": round(avg_trust, 4),
            "categories": len(self.list_categories()),
        }


# ── Module-level singleton ──────────────────────────────────────────────
_registry: Optional[GlobalAgentRegistry] = None


def get_global_agent_registry() -> GlobalAgentRegistry:
    """Return the process-wide GlobalAgentRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = GlobalAgentRegistry()
    return _registry
