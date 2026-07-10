"""
Plugin SDK (M10.4 — Plugin SDK).

Layer: Adapters / Interface — formalizes the plugin development surface
so third-party developers can extend Agent Reach without modifying the
platform core.

The SDK provides abstract base classes for every extensible subsystem:
- PluginProvider — custom model providers
- PluginTool — custom tools
- PluginMemoryAdapter — custom memory backends
- PluginContextEngine — custom context engines
- PluginRouter — custom provider routers
- PluginSkill — custom skills
- PluginBenchmark — custom benchmark suites
- PluginVisualNode — custom visual workflow nodes

Each base class declares the contract a plugin must implement. Plugins
register via a manifest (see PluginManifest) and are loaded by the
existing DynamicPluginLoader (no core changes needed).

This module is intentionally dependency-free (only stdlib + typing) so
it can be distributed as a standalone pip-installable SDK package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ── Plugin type enum ────────────────────────────────────────────────────

class PluginType(str):
    """String constants for the plugin types supported by the SDK."""
    PROVIDER = "provider"
    TOOL = "tool"
    MEMORY_ADAPTER = "memory_adapter"
    CONTEXT_ENGINE = "context_engine"
    ROUTER = "router"
    SKILL = "skill"
    BENCHMARK = "benchmark"
    VISUAL_NODE = "visual_node"
    AGENT = "agent"


# ── Manifest ───────────────────────────────────────────────────────────

@dataclass
class PluginManifest:
    """Declares a plugin's identity, type, and entry point.

    A plugin's manifest.yaml or manifest.json must deserialize into
    this structure. The platform's DynamicPluginLoader reads it and
    instantiates the entry_point class.
    """
    plugin_id: str
    name: str
    version: str  # semver
    plugin_type: str  # one of PluginType.*
    description: str = ""
    author: str = ""
    homepage: str = ""
    license: str = "MIT"
    min_platform_version: str = "10.0.0"
    entry_point: str = ""  # dotted path to the plugin class, e.g. "my_plugin:MyProvider"
    config_schema: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "plugin_type": self.plugin_type,
            "description": self.description,
            "author": self.author,
            "homepage": self.homepage,
            "license": self.license,
            "min_platform_version": self.min_platform_version,
            "entry_point": self.entry_point,
            "config_schema": dict(self.config_schema),
            "dependencies": list(self.dependencies),
            "tags": list(self.tags),
        }


# ── Abstract base classes for each plugin type ─────────────────────────

class PluginBase(ABC):
    """Common base for all plugins. Provides config + lifecycle hooks."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        self.config = config or {}

    def initialize(self) -> None:
        """Called once after construction. Override for setup."""

    def shutdown(self) -> None:
        """Called when the plugin is being retired. Override for cleanup."""

    @property
    @abstractmethod
    def manifest(self) -> PluginManifest:
        """The plugin's manifest. Subclasses must return their manifest."""


class PluginProvider(PluginBase):
    """Custom model provider (e.g. a new LLM vendor)."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        """Send messages to the model and return the text reply."""


class PluginTool(PluginBase):
    """Custom tool that agents can call during execution."""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Run the tool with the given keyword arguments."""

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """The tool's unique name (e.g. 'web_search')."""

    @property
    def description(self) -> str:
        return ""


class PluginMemoryAdapter(PluginBase):
    """Custom memory backend (e.g. Redis, Postgres, vector DB)."""

    @abstractmethod
    def store(self, content: str, importance: float = 0.5, metadata: Optional[dict] = None) -> str:
        """Store a memory item. Returns its ID."""

    @abstractmethod
    def retrieve_relevant(self, query: str, count: int = 5) -> list[Any]:
        """Return the most relevant memory items for the query."""

    @abstractmethod
    def clear(self) -> None:
        """Drop all stored memories."""


class PluginContextEngine(PluginBase):
    """Custom context engine for building model prompts."""

    @abstractmethod
    def build(self, system: str, memories: list[str], conversation: list[dict], query: str) -> str:
        """Assemble the full context string for a model call."""


class PluginRouter(PluginBase):
    """Custom provider router for selecting the best model per request."""

    @abstractmethod
    def select_provider(self, query: str, available_providers: list[str]) -> str:
        """Pick a provider from available_providers for the given query."""


class PluginSkill(PluginBase):
    """Custom skill (a reusable capability package)."""

    @abstractmethod
    async def apply(self, context: dict[str, Any]) -> Any:
        """Apply the skill in the given context."""


class PluginBenchmark(PluginBase):
    """Custom benchmark suite for evaluating providers or agents."""

    @abstractmethod
    async def run(self, target: str) -> dict[str, Any]:
        """Run the benchmark against the named target. Returns metrics."""


class PluginVisualNode(PluginBase):
    """Custom node type for the Visual Workflow Builder."""

    @property
    @abstractmethod
    def node_type(self) -> str:
        """The node's unique type identifier."""

    @property
    def inputs(self) -> list[str]:
        return []

    @property
    def outputs(self) -> list[str]:
        return []

    @abstractmethod
    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the node with the given inputs. Returns outputs."""


# ── Registry of loaded plugins ──────────────────────────────────────────

class PluginSDKRegistry:
    """Tracks all SDK-compliant plugins loaded by the platform.

    This is separate from the existing PluginManager (which handles the
    older plugin/capability system). The two coexist: SDK plugins are
    registered here; legacy plugins continue to use PluginManager.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, PluginBase] = {}
        self._manifests: dict[str, PluginManifest] = {}

    def register(self, plugin: PluginBase, manifest: PluginManifest) -> None:
        self._plugins[manifest.plugin_id] = plugin
        self._manifests[manifest.plugin_id] = manifest

    def unregister(self, plugin_id: str) -> bool:
        existed = self._plugins.pop(plugin_id, None) is not None
        self._manifests.pop(plugin_id, None)
        return existed

    def get(self, plugin_id: str) -> Optional[PluginBase]:
        return self._plugins.get(plugin_id)

    def list_by_type(self, plugin_type: str) -> list[tuple[str, PluginManifest]]:
        return [
            (pid, m) for pid, m in self._manifests.items()
            if m.plugin_type == plugin_type
        ]

    def list_all(self) -> list[PluginManifest]:
        return list(self._manifests.values())

    def stats(self) -> dict[str, Any]:
        from collections import Counter
        type_counts = Counter(m.plugin_type for m in self._manifests.values())
        return {
            "total": len(self._manifests),
            "by_type": dict(type_counts),
        }


# ── Module-level singleton ──────────────────────────────────────────────

_sdk_registry: Optional[PluginSDKRegistry] = None


def get_plugin_sdk_registry() -> PluginSDKRegistry:
    """Return the process-wide PluginSDKRegistry singleton."""
    global _sdk_registry
    if _sdk_registry is None:
        _sdk_registry = PluginSDKRegistry()
    return _sdk_registry
