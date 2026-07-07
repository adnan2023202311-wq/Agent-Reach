"""
Agents layer: Agent Registry 2.0 (M6.5).

Layer: Adapters — extends the agent registration in composition.py
with dynamic registration, dependency validation, versioning,
enable/disable, and metadata.

The existing ``build_default_agent_registry()`` in composition.py
creates a static dict of agents at startup. AgentRegistry adds the
management surface on top:

- **dynamic registration**: register/unregister agents at runtime
- **dependency validation**: declare and validate agent dependencies
- **versioning**: each agent carries a version string
- **enable/disable**: agents can be deactivated without unregistering
- **metadata**: name, description, version, dependencies, tags

AgentRegistry wraps the existing agent registration pattern — it does
not replace composition.py. It provides a richer registry that the
composition root can use to build the final agent dict for
AgentDispatcher.

Design notes
------------
- AgentRegistry is a registry of agents by AgentType. Each AgentType
  maps to exactly one Agent instance (same as the existing pattern).
- Dependencies are declared as a list of strings (e.g. tool names,
  provider names). Validation checks that each dependency is available
  in the provided dependency providers (tools, providers).
- Disabling an agent removes it from the active registry but keeps its
  metadata, so it can be re-enabled without re-registering.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from domain.interfaces import Agent
from domain.models import AgentType

logger = logging.getLogger(__name__)


@dataclass
class AgentMetadata:
    """Metadata for a registered agent.

    Attributes:
        agent_id: unique identifier (stable across re-registrations).
        agent_type: the AgentType this agent handles.
        name: human-readable name.
        description: short description of the agent's capabilities.
        version: semantic version string.
        dependencies: list of dependency identifiers (tools, providers).
        tags: arbitrary string tags for search/filtering.
        enabled: whether the agent is active.
        registered_at: ISO-8601 timestamp of first registration.
        updated_at: ISO-8601 timestamp of last metadata change.
    """

    agent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_type: AgentType = AgentType.RESEARCH
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    enabled: bool = True
    registered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type.value,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "dependencies": list(self.dependencies),
            "tags": list(self.tags),
            "enabled": self.enabled,
            "registered_at": self.registered_at,
            "updated_at": self.updated_at,
        }


class AgentRegistry:
    """Dynamic agent registry with metadata and dependency validation.

    Parameters
    ---
    initial_agents:
        Optional mapping of AgentType → Agent to pre-populate the
        registry. Used to seed with the default agents from
        composition.py.
    """

    def __init__(
        self,
        initial_agents: Optional[dict[AgentType, Agent]] = None,
    ) -> None:
        self._agents: dict[AgentType, Agent] = {}
        self._metadata: dict[AgentType, AgentMetadata] = {}
        self._dependency_providers: dict[str, set[str]] = {
            "tools": set(),
            "providers": set(),
        }

        if initial_agents:
            for agent_type, agent in initial_agents.items():
                self.register(agent, agent_type=agent_type)

    # ------------------------------------------------------------------
    # Dependency providers
    # ------------------------------------------------------------------

    def set_dependency_providers(
        self,
        category: str,
        providers: set[str],
    ) -> None:
        """Set the available providers for a dependency category.

        Categories are free-form strings — common ones are "tools" and
        "providers". When ``validate_dependencies`` is called, each
        dependency in an agent's dependency list is checked against
        the providers in the matching category.
        """
        self._dependency_providers[category] = set(providers)

    def add_dependency_provider(self, category: str, name: str) -> None:
        """Add a single provider to a dependency category."""
        self._dependency_providers.setdefault(category, set()).add(name)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        agent: Agent,
        *,
        agent_type: Optional[AgentType] = None,
        name: str = "",
        description: str = "",
        version: str = "1.0.0",
        dependencies: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        enabled: bool = True,
    ) -> AgentMetadata:
        """Register an agent with metadata.

        If an agent for the same AgentType is already registered, its
        metadata is updated but the agent_id is preserved.

        Returns the AgentMetadata for the registered agent.
        """
        now = datetime.now(timezone.utc).isoformat()
        at = agent_type or agent.agent_type

        if at in self._metadata:
            # Update existing — preserve agent_id and registered_at.
            meta = self._metadata[at]
            meta.name = name or meta.name or at.value.replace("_", " ").title()
            meta.description = description or meta.description
            meta.version = version
            meta.dependencies = list(dependencies) if dependencies is not None else meta.dependencies
            meta.tags = list(tags) if tags is not None else meta.tags
            meta.enabled = enabled
            meta.updated_at = now
        else:
            meta = AgentMetadata(
                agent_type=at,
                name=name or at.value.replace("_", " ").title(),
                description=description,
                version=version,
                dependencies=list(dependencies or []),
                tags=list(tags or []),
                enabled=enabled,
                registered_at=now,
                updated_at=now,
            )
            self._metadata[at] = meta

        self._agents[at] = agent
        logger.info("Registered agent: %s (v%s)", at.value, version)
        return meta

    def unregister(self, agent_type: AgentType) -> bool:
        """Remove an agent from the registry.

        Returns True if the agent was removed, False if it was not
        registered.
        """
        if agent_type not in self._metadata:
            return False
        del self._metadata[agent_type]
        del self._agents[agent_type]
        logger.info("Unregistered agent: %s", agent_type.value)
        return True

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    def enable(self, agent_type: AgentType) -> bool:
        """Enable an agent. Returns True if the agent exists."""
        if agent_type not in self._metadata:
            return False
        self._metadata[agent_type].enabled = True
        self._metadata[agent_type].updated_at = datetime.now(timezone.utc).isoformat()
        return True

    def disable(self, agent_type: AgentType) -> bool:
        """Disable an agent. Returns True if the agent exists."""
        if agent_type not in self._metadata:
            return False
        self._metadata[agent_type].enabled = False
        self._metadata[agent_type].updated_at = datetime.now(timezone.utc).isoformat()
        return True

    def is_enabled(self, agent_type: AgentType) -> bool:
        """Whether an agent is registered and enabled."""
        meta = self._metadata.get(agent_type)
        return meta is not None and meta.enabled

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def get_agent(self, agent_type: AgentType) -> Optional[Agent]:
        """Return the agent for a type, or None if not registered."""
        return self._agents.get(agent_type)

    def get_metadata(self, agent_type: AgentType) -> Optional[AgentMetadata]:
        """Return the metadata for an agent type, or None."""
        return self._metadata.get(agent_type)

    def get_enabled_agents(self) -> dict[AgentType, Agent]:
        """Return a dict of enabled agents (for AgentDispatcher)."""
        return {
            at: agent
            for at, agent in self._agents.items()
            if self._metadata.get(at, AgentMetadata()).enabled
        }

    def list_metadata(
        self,
        *,
        enabled_only: bool = False,
        tag: str = "",
    ) -> list[AgentMetadata]:
        """List agent metadata, optionally filtered."""
        results: list[AgentMetadata] = []
        for meta in self._metadata.values():
            if enabled_only and not meta.enabled:
                continue
            if tag and tag not in meta.tags:
                continue
            results.append(meta)
        return sorted(results, key=lambda m: m.agent_type.value)

    # ------------------------------------------------------------------
    # Dependency validation
    # ------------------------------------------------------------------

    def validate_dependencies(
        self, agent_type: AgentType
    ) -> list[str]:
        """Validate an agent's dependencies.

        Returns a list of missing dependencies (empty if all are met).

        Each dependency string is expected to be in the form
        ``"category:name"`` (e.g. ``"tools:git_clone"``,
        ``"providers:openai"``). If no category prefix is given, the
        dependency is checked against all categories.
        """
        meta = self._metadata.get(agent_type)
        if meta is None:
            return [f"Agent '{agent_type.value}' is not registered"]

        missing: list[str] = []
        for dep in meta.dependencies:
            if ":" in dep:
                category, name = dep.split(":", 1)
                available = self._dependency_providers.get(category, set())
                if name not in available:
                    missing.append(dep)
            else:
                # No category prefix — check all categories.
                found = any(
                    dep in providers
                    for providers in self._dependency_providers.values()
                )
                if not found:
                    missing.append(dep)
        return missing

    def validate_all(self) -> dict[AgentType, list[str]]:
        """Validate dependencies for all registered agents.

        Returns a mapping of AgentType → list of missing dependencies.
        Only agents with missing dependencies are included.
        """
        issues: dict[AgentType, list[str]] = {}
        for agent_type in self._metadata:
            missing = self.validate_dependencies(agent_type)
            if missing:
                issues[agent_type] = missing
        return issues

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics about the registry."""
        total = len(self._metadata)
        enabled = sum(1 for m in self._metadata.values() if m.enabled)
        return {
            "total": total,
            "enabled": enabled,
            "disabled": total - enabled,
        }

    def clear(self) -> None:
        """Remove all agents. Useful for testing."""
        self._agents.clear()
        self._metadata.clear()
