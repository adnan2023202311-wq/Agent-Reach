"""
Capability Resolver for Milestone 4.

Per ADR-005: Capability Resolver is mandatory. Planner MUST never call
tools directly. The resolver maps capability identifiers to concrete
executors (agents, tools, skills, or MCP tools).

Layer: Application/Core — depends inward on domain/ and infrastructure/ only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


@dataclass
class ResolvedCapability:
    """Result of resolving a capability ID to a concrete executor."""

    capability_id: str
    executor: Callable[..., Awaitable[Any]]
    metadata: dict[str, Any] = field(default_factory=dict)
    fallback: bool = False


class CapabilityResolver:
    """Maps capability identifiers to concrete executors.

    The resolver is the single gateway through which the Planner,
    Workflow Engine, and Skill Engine access tools and agents.
    No component above the resolver should hold direct references
    to executors.
    """

    def __init__(self) -> None:
        self._executors: dict[str, Callable[..., Awaitable[Any]]] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._fallbacks: dict[str, str] = {}

    def register(
        self,
        capability_id: str,
        executor: Callable[..., Awaitable[Any]],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register an executor for a capability ID."""
        self._executors[capability_id] = executor
        self._metadata[capability_id] = metadata or {}

    def unregister(self, capability_id: str) -> bool:
        """Remove a capability registration."""
        if capability_id not in self._executors:
            return False
        del self._executors[capability_id]
        self._metadata.pop(capability_id, None)
        self._fallbacks.pop(capability_id, None)
        return True

    def set_fallback(self, capability_id: str, fallback_id: str) -> None:
        """Set a fallback capability ID if primary resolution fails."""
        self._fallbacks[capability_id] = fallback_id

    def resolve(self, capability_id: str) -> Optional[ResolvedCapability]:
        """Resolve a capability ID to its executor.

        Returns None if the capability is not registered and has no
        usable fallback.
        """
        executor = self._executors.get(capability_id)
        metadata = self._metadata.get(capability_id, {})
        is_fallback = False

        if executor is None:
            fallback_id = self._fallbacks.get(capability_id)
            if fallback_id and fallback_id in self._executors:
                executor = self._executors[fallback_id]
                metadata = self._metadata.get(fallback_id, {})
                is_fallback = True
            else:
                return None

        return ResolvedCapability(
            capability_id=capability_id,
            executor=executor,
            metadata=metadata,
            fallback=is_fallback,
        )

    def has_capability(self, capability_id: str) -> bool:
        """Check whether a capability can be resolved."""
        if capability_id in self._executors:
            return True
        fallback_id = self._fallbacks.get(capability_id)
        return fallback_id is not None and fallback_id in self._executors

    def list_capabilities(self) -> list[str]:
        """List all registered capability IDs."""
        return list(self._executors.keys())

    def get_metadata(self, capability_id: str) -> dict[str, Any]:
        """Return metadata for a capability."""
        return dict(self._metadata.get(capability_id, {}))

    def clear(self) -> None:
        """Remove all registrations. Useful for testing."""
        self._executors.clear()
        self._metadata.clear()
        self._fallbacks.clear()
