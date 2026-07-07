"""
Infrastructure layer: Tool Registry 2.0 (M6.4).

Layer: Adapters — extends infrastructure/tool_manager.py with
discovery, versioning, metadata, permissions, enable/disable, and
categories.

The existing ToolManager handles the core mechanism (registration,
permission check, audit log, execution). ToolRegistry adds the
management surface on top:

- **discovery**: list tools with filtering by category, enabled state
- **versioning**: each tool carries a semantic version string
- **metadata**: name, description, category, tags, version
- **permissions**: which agent types may call the tool (reuses the
  existing ToolManager permission model)
- **enable/disable**: tools can be deactivated without unregistering
- **categories**: tools are grouped by a category string

The ToolRegistry delegates execution to the ToolManager it wraps —
it does not duplicate the permission/audit logic. It only adds the
metadata layer and the enable/disable gate.

Design notes
------------
- ToolRegistry wraps a ToolManager instance (injected, not constructed
  internally) so tests can pass a fresh ToolManager and production
  code can pass the shared one from composition.py.
- Disabling a tool raises KeyError on call (same as an unregistered
  tool) so callers get a consistent "not available" signal.
- Categories are free-form strings — no fixed enum. A tool with an
  empty category is "uncategorized".
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from infrastructure.tool_manager import ToolManager


class ToolFunc(Protocol):
    async def __call__(self, **kwargs: Any) -> Any: ...


logger = logging.getLogger(__name__)


@dataclass
class ToolMetadata:
    """Metadata for a registered tool.

    Attributes:
        tool_id: unique identifier (stable across re-registrations).
        name: human-readable name (unique among registered tools).
        description: short description of what the tool does.
        version: semantic version string (e.g. "1.0.0").
        category: grouping string (e.g. "git", "filesystem").
        tags: arbitrary string tags for search/filtering.
        enabled: whether the tool can be called.
        allowed_agents: agent types permitted to call this tool.
            Empty set means "no restriction".
        created_at: ISO-8601 timestamp of first registration.
        updated_at: ISO-8601 timestamp of last metadata change.
        call_count: number of times the tool has been called.
    """

    tool_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    category: str = ""
    tags: list[str] = field(default_factory=list)
    enabled: bool = True
    allowed_agents: frozenset[str] = field(default_factory=frozenset)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    call_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "category": self.category,
            "tags": list(self.tags),
            "enabled": self.enabled,
            "allowed_agents": sorted(self.allowed_agents),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "call_count": self.call_count,
        }


class ToolRegistry:
    """Extended tool registry with metadata, versioning, and lifecycle.

    Parameters
    ---
    manager:
        The underlying ToolManager that handles execution. Injected.
    """

    def __init__(self, manager: Optional[ToolManager] = None) -> None:
        self._manager = manager or ToolManager()
        self._metadata: dict[str, ToolMetadata] = {}
        self._funcs: dict[str, ToolFunc] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        func: ToolFunc,
        *,
        description: str = "",
        version: str = "1.0.0",
        category: str = "",
        tags: Optional[list[str]] = None,
        allowed_agents: Optional[frozenset[str]] = None,
        enabled: bool = True,
    ) -> ToolMetadata:
        """Register a tool with metadata.

        If a tool with the same name is already registered, its metadata
        is updated (version bump, description change, etc.) but the
        tool_id is preserved.

        Returns the ToolMetadata for the registered tool.
        """
        now = datetime.now(timezone.utc).isoformat()

        if name in self._metadata:
            # Update existing — preserve tool_id and created_at.
            meta = self._metadata[name]
            meta.description = description or meta.description
            meta.version = version
            meta.category = category or meta.category
            meta.tags = list(tags) if tags is not None else meta.tags
            meta.enabled = enabled
            meta.allowed_agents = allowed_agents if allowed_agents is not None else meta.allowed_agents
            meta.updated_at = now
        else:
            meta = ToolMetadata(
                name=name,
                description=description,
                version=version,
                category=category,
                tags=list(tags or []),
                enabled=enabled,
                allowed_agents=allowed_agents or frozenset(),
                created_at=now,
                updated_at=now,
            )
            self._metadata[name] = meta

        # Store the function and register with the underlying manager.
        self._funcs[name] = func
        self._manager.register(name, func, allowed_agents=meta.allowed_agents)

        logger.info("Registered tool: %s (v%s)", name, version)
        return meta

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry.

        Returns True if the tool was removed, False if it was not
        registered.
        """
        if name not in self._metadata:
            return False
        del self._metadata[name]
        del self._funcs[name]
        # The underlying ToolManager has no unregister, so we replace
        # it with a fresh one that has all tools except the removed one.
        self._rebuild_manager()
        logger.info("Unregistered tool: %s", name)
        return True

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    def enable(self, name: str) -> bool:
        """Enable a tool. Returns True if the tool exists."""
        if name not in self._metadata:
            return False
        self._metadata[name].enabled = True
        self._metadata[name].updated_at = datetime.now(timezone.utc).isoformat()
        return True

    def disable(self, name: str) -> bool:
        """Disable a tool. Returns True if the tool exists."""
        if name not in self._metadata:
            return False
        self._metadata[name].enabled = False
        self._metadata[name].updated_at = datetime.now(timezone.utc).isoformat()
        return True

    def is_enabled(self, name: str) -> bool:
        """Whether a tool is registered and enabled."""
        meta = self._metadata.get(name)
        return meta is not None and meta.enabled

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def call(self, name: str, agent_type: str, **kwargs: Any) -> Any:
        """Call a tool by name.

        Raises
        ------
        KeyError:
            If the tool is not registered or is disabled.
        PermissionError:
            If the agent_type is not permitted to use the tool.
        """
        meta = self._metadata.get(name)
        if meta is None:
            raise KeyError(f"Tool '{name}' is not registered")
        if not meta.enabled:
            raise KeyError(f"Tool '{name}' is disabled")

        meta.call_count += 1
        return await self._manager.call(name, agent_type, **kwargs)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def get_metadata(self, name: str) -> Optional[ToolMetadata]:
        """Return the metadata for a tool, or None if not registered."""
        return self._metadata.get(name)

    def list_tools(
        self,
        *,
        category: str = "",
        enabled_only: bool = False,
        tag: str = "",
    ) -> list[ToolMetadata]:
        """List tool metadata, optionally filtered.

        Parameters
        ----------
        category:
            If non-empty, only tools in this category are returned.
        enabled_only:
            If True, only enabled tools are returned.
        tag:
            If non-empty, only tools with this tag are returned.
        """
        results: list[ToolMetadata] = []
        for meta in self._metadata.values():
            if enabled_only and not meta.enabled:
                continue
            if category and meta.category != category:
                continue
            if tag and tag not in meta.tags:
                continue
            results.append(meta)
        return sorted(results, key=lambda m: m.name)

    def list_categories(self) -> list[str]:
        """Return all distinct category strings, sorted.

        Tools with an empty category are grouped under "uncategorized".
        """
        categories: set[str] = set()
        for meta in self._metadata.values():
            categories.add(meta.category or "uncategorized")
        return sorted(categories)

    def list_tags(self) -> list[str]:
        """Return all distinct tags across all tools, sorted."""
        tags: set[str] = set()
        for meta in self._metadata.values():
            tags.update(meta.tags)
        return sorted(tags)

    def search(self, query: str) -> list[ToolMetadata]:
        """Search tools by name, description, or tags (case-insensitive).

        A tool matches if the query appears as a substring of its name,
        description, or any of its tags.
        """
        q = query.lower()
        results: list[ToolMetadata] = []
        for meta in self._metadata.values():
            if (
                q in meta.name.lower()
                or q in meta.description.lower()
                or any(q in t.lower() for t in meta.tags)
            ):
                results.append(meta)
        return sorted(results, key=lambda m: m.name)

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics about the registry."""
        total = len(self._metadata)
        enabled = sum(1 for m in self._metadata.values() if m.enabled)
        disabled = total - enabled
        categories = len(self.list_categories())
        total_calls = sum(m.call_count for m in self._metadata.values())
        return {
            "total": total,
            "enabled": enabled,
            "disabled": disabled,
            "categories": categories,
            "total_calls": total_calls,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rebuild_manager(self) -> None:
        """Rebuild the underlying ToolManager with the current tools.

        Used after unregister since ToolManager has no unregister method.
        """
        new_manager = ToolManager()
        for name, meta in self._metadata.items():
            if name in self._funcs:
                new_manager.register(
                    name,
                    self._funcs[name],
                    allowed_agents=meta.allowed_agents,
                )
        self._manager = new_manager

    def clear(self) -> None:
        """Remove all tools. Useful for testing."""
        self._metadata.clear()
        self._funcs.clear()
        self._manager = ToolManager()
