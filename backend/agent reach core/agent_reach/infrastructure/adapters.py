"""
Future AI Layer (M9.26) — technology-agnostic adapter registry.

Layer: Adapters/Infrastructure.

M9.26 requires supporting future providers, plugins, tools, memory
systems, context systems, and routers "with no core modifications".
The mechanism that makes this true:

- Each category has a REQUIRED INTERFACE — the exact method set the
  existing runtime already calls on that subsystem (derived from how
  IntelligentPipeline / ToolRegistry / ProviderManager use them
  today). An adapter is any object implementing those methods.
- AdapterRegistry.register() validates structurally (methods present
  and callable, async where the runtime awaits them) and rejects
  non-conforming adapters with a precise error — no duck-typing
  surprises at request time.
- Activation binds a registered adapter into the LIVE runtime:
  memory/context/router adapters swap into the shared
  IntelligentPipeline through its public use_subsystem() extension
  point; tool adapters register into the live ToolRegistry. The
  core pipeline code is untouched — that is the point.

Providers deliberately have no API-level activation: a provider
adapter needs credentials and a ModelClient contract, and swapping
the model client is composition.py's job. They can still be
registered and validated here for introspection.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Optional


class AdapterValidationError(Exception):
    """The adapter does not implement its category's required interface."""


@dataclass(frozen=True)
class MethodSpec:
    """One required method: name + whether the runtime awaits it."""

    name: str
    must_be_async: bool = False


@dataclass(frozen=True)
class CategorySpec:
    """The interface one adapter category must implement.

    ``methods`` mirrors exactly what the existing runtime calls on
    that subsystem — nothing speculative.
    """

    category: str
    description: str
    methods: tuple[MethodSpec, ...]


# Interfaces derived from real call sites:
# - memory:  IntelligentPipeline._step_memory + memory router
# - context: IntelligentPipeline._step_context
# - router:  IntelligentPipeline._step_router + providers router
# - tool:    ToolRegistry.register expects an async callable
# - provider: domain.interfaces.ModelClient contract
# - plugin:  agent-reach-core plugin execute contract
CATEGORY_SPECS: dict[str, CategorySpec] = {
    "memory": CategorySpec(
        category="memory",
        description="Memory engine (LongCat-compatible surface used by the pipeline).",
        methods=(
            MethodSpec("store"),
            MethodSpec("retrieve_relevant"),
            MethodSpec("get_stats"),
            MethodSpec("clear"),
        ),
    ),
    "context": CategorySpec(
        category="context",
        description="Context engine surface used by the pipeline.",
        methods=(
            MethodSpec("add"),
            MethodSpec("build_with_sources"),
            MethodSpec("get_stats"),
            MethodSpec("clear"),
        ),
    ),
    "router": CategorySpec(
        category="router",
        description="Intelligence router surface used by the pipeline.",
        methods=(
            MethodSpec("select_provider"),
            MethodSpec("list_providers"),
            MethodSpec("get_provider_health"),
        ),
    ),
    "tool": CategorySpec(
        category="tool",
        description="Async-callable tool (ToolRegistry contract).",
        methods=(MethodSpec("__call__", must_be_async=True),),
    ),
    "provider": CategorySpec(
        category="provider",
        description="ModelClient contract (async complete()).",
        methods=(MethodSpec("complete", must_be_async=True),),
    ),
    "plugin": CategorySpec(
        category="plugin",
        description="Plugin execution contract (async execute()).",
        methods=(MethodSpec("execute", must_be_async=True),),
    ),
}

# Categories whose adapters the pipeline can hot-swap.
_PIPELINE_SUBSYSTEMS = {"memory", "context", "router"}


@dataclass
class RegisteredAdapter:
    """One validated adapter."""

    category: str
    name: str
    adapter: Any
    description: str = ""
    active: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "name": self.name,
            "type": type(self.adapter).__name__,
            "description": self.description,
            "active": self.active,
            "metadata": dict(self.metadata),
        }


class AdapterRegistry:
    """Validate, hold, and activate technology adapters."""

    def __init__(self, pipeline: Any, tool_runtime: Any = None) -> None:
        self._pipeline = pipeline
        self._tool_runtime = tool_runtime
        self._adapters: dict[tuple[str, str], RegisteredAdapter] = {}

    # ── Validation & registration ───────────────────────────────

    @staticmethod
    def validate(category: str, adapter: Any) -> list[str]:
        """Return the list of interface problems (empty = valid)."""
        spec = CATEGORY_SPECS.get(category)
        if spec is None:
            return [f"Unknown category '{category}'. Valid: {sorted(CATEGORY_SPECS)}"]
        problems: list[str] = []
        for method in spec.methods:
            attr = getattr(adapter, method.name, None)
            if attr is None or not callable(attr):
                problems.append(
                    f"missing required method '{method.name}'"
                )
                continue
            if method.must_be_async and not inspect.iscoroutinefunction(
                inspect.unwrap(attr)
            ):
                # bound __call__ on an instance: check the underlying func
                func = getattr(attr, "__func__", attr)
                if not inspect.iscoroutinefunction(func):
                    problems.append(
                        f"method '{method.name}' must be async (the runtime awaits it)"
                    )
        return problems

    def register(
        self,
        category: str,
        name: str,
        adapter: Any,
        description: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> RegisteredAdapter:
        """Validate and register an adapter. Raises on violations."""
        if not name.strip():
            raise ValueError("adapter name must not be empty")
        problems = self.validate(category, adapter)
        if problems:
            raise AdapterValidationError(
                f"Adapter '{name}' does not satisfy the '{category}' "
                f"interface: {problems}"
            )
        registered = RegisteredAdapter(
            category=category,
            name=name.strip(),
            adapter=adapter,
            description=description,
            metadata=dict(metadata or {}),
        )
        self._adapters[(category, registered.name)] = registered
        return registered

    def unregister(self, category: str, name: str) -> bool:
        return self._adapters.pop((category, name), None) is not None

    # ── Activation ──────────────────────────────────────────────

    def activate(self, category: str, name: str) -> RegisteredAdapter:
        """Bind a registered adapter into the live runtime.

        - memory/context/router → pipeline.use_subsystem() (the
          public M9.26 extension point; core code untouched).
        - tool → registered into the live ToolRegistry.
        - provider/plugin → not activatable at runtime (credentials /
          plugin-manager lifecycle are composition concerns); raises.
        """
        registered = self._adapters.get((category, name))
        if registered is None:
            raise KeyError(f"No adapter '{name}' registered in '{category}'")

        if category in _PIPELINE_SUBSYSTEMS:
            self._pipeline.use_subsystem(category, registered.adapter)
        elif category == "tool":
            if self._tool_runtime is None:
                raise RuntimeError("No tool runtime attached to the adapter registry")
            self._tool_runtime.registry.register(
                name,
                registered.adapter,
                description=registered.description
                or f"Adapter-registered tool '{name}'",
                category="adapter",
                tags=["adapter", "future-ai"],
            )
        else:
            raise AdapterActivationUnsupported(
                f"Category '{category}' adapters are validated and "
                "introspectable but must be wired in the composition "
                "root (credentials / lifecycle), not activated via API."
            )

        # Only one active adapter per pipeline subsystem.
        if category in _PIPELINE_SUBSYSTEMS:
            for (cat, other_name), other in self._adapters.items():
                if cat == category and other_name != name:
                    other.active = False
        registered.active = True
        return registered

    # ── Introspection ───────────────────────────────────────────

    def list_adapters(self, category: str = "") -> list[RegisteredAdapter]:
        adapters = list(self._adapters.values())
        if category:
            adapters = [a for a in adapters if a.category == category]
        return sorted(adapters, key=lambda a: (a.category, a.name))

    def get(self, category: str, name: str) -> Optional[RegisteredAdapter]:
        return self._adapters.get((category, name))

    @staticmethod
    def describe_categories() -> dict[str, Any]:
        return {
            spec.category: {
                "description": spec.description,
                "required_methods": [
                    {"name": m.name, "async": m.must_be_async}
                    for m in spec.methods
                ],
                "runtime_activatable": spec.category
                in (_PIPELINE_SUBSYSTEMS | {"tool"}),
            }
            for spec in CATEGORY_SPECS.values()
        }

    def clear(self) -> None:
        self._adapters.clear()


class AdapterActivationUnsupported(Exception):
    """This category cannot be activated at runtime via the API."""
