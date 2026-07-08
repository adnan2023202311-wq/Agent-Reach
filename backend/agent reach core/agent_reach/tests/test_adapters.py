"""Tests for M9.26 — Future AI Layer (adapter registry).

Proves: structural validation against the real runtime interfaces
(missing methods and sync-where-async-required rejected with precise
errors), live activation into the SHARED pipeline via use_subsystem
(a swapped memory adapter genuinely serves the next request), tool
adapter activation into the live ToolRegistry, single-active-adapter
semantics, honest refusal for provider/plugin runtime activation,
and the API surface.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from composition import build_intelligent_pipeline, build_tool_runtime
from config.settings import get_settings
from infrastructure.adapters import (
    AdapterActivationUnsupported,
    AdapterRegistry,
    AdapterValidationError,
)


# ── Test adapters ───────────────────────────────────────────────


class _RecordingMemoryAdapter:
    """A LongCat-compatible memory adapter that records calls."""

    def __init__(self) -> None:
        self.stored: list[str] = []
        self.working_memory: list[Any] = []

    def store(self, content: Any, importance: float = 0.5,
              metadata: Any = None, add_to_working: bool = True) -> str:
        self.stored.append(str(content))
        return f"mem_{len(self.stored)}"

    def retrieve_relevant(self, count: int = 10, query: str = "") -> list[Any]:
        return []

    def get_stats(self) -> dict[str, Any]:
        return {"memory_counts": {"total": len(self.stored)}}

    def clear(self) -> None:
        self.stored.clear()


class _BrokenMemoryAdapter:
    """Missing retrieve_relevant — must be rejected."""

    def store(self, *a: Any, **k: Any) -> str:
        return "x"

    def get_stats(self) -> dict[str, Any]:
        return {}

    def clear(self) -> None:
        pass


class _SyncToolAdapter:
    """Sync __call__ where the runtime awaits — must be rejected."""

    def __call__(self, **kwargs: Any) -> str:
        return "sync result"


class _AsyncToolAdapter:
    async def __call__(self, **kwargs: Any) -> str:
        return f"adapter tool ran with {kwargs}"


class _ProviderAdapter:
    async def complete(self, messages: Any, *, system: Any = None,
                       max_tokens: int = 1024) -> str:
        return "provider reply"


# ===========================================================================
# Validation
# ===========================================================================


class TestValidation:
    def _registry(self) -> AdapterRegistry:
        return AdapterRegistry(build_intelligent_pipeline())

    def test_valid_memory_adapter_accepted(self) -> None:
        registry = self._registry()
        registered = registry.register("memory", "recorder", _RecordingMemoryAdapter())
        assert registered.active is False
        assert registry.get("memory", "recorder") is registered

    def test_missing_method_rejected_precisely(self) -> None:
        registry = self._registry()
        with pytest.raises(AdapterValidationError, match="retrieve_relevant"):
            registry.register("memory", "broken", _BrokenMemoryAdapter())

    def test_sync_where_async_required_rejected(self) -> None:
        registry = self._registry()
        with pytest.raises(AdapterValidationError, match="must be async"):
            registry.register("tool", "sync_tool", _SyncToolAdapter())

    def test_unknown_category_rejected(self) -> None:
        registry = self._registry()
        problems = registry.validate("teleporter", object())
        assert "Unknown category" in problems[0]

    def test_empty_name_rejected(self) -> None:
        registry = self._registry()
        with pytest.raises(ValueError):
            registry.register("memory", "  ", _RecordingMemoryAdapter())

    def test_provider_adapter_validates(self) -> None:
        registry = self._registry()
        registered = registry.register("provider", "fake", _ProviderAdapter())
        assert registered.category == "provider"


# ===========================================================================
# Activation
# ===========================================================================


@pytest.mark.asyncio
class TestActivation:
    async def test_memory_adapter_serves_real_requests(self) -> None:
        """The swapped adapter genuinely receives pipeline traffic."""
        pipeline = build_intelligent_pipeline()
        registry = AdapterRegistry(pipeline)
        adapter = _RecordingMemoryAdapter()
        registry.register("memory", "recorder", adapter)
        registry.activate("memory", "recorder")

        await pipeline.process("store this in the adapter")
        assert len(adapter.stored) == 1
        assert "store this in the adapter" in adapter.stored[0]

    async def test_tool_adapter_lands_in_live_registry(self) -> None:
        pipeline = build_intelligent_pipeline()
        tool_runtime = build_tool_runtime()
        registry = AdapterRegistry(pipeline, tool_runtime)
        registry.register("tool", "adapter_tool", _AsyncToolAdapter())
        registry.activate("tool", "adapter_tool")

        meta = tool_runtime.registry.get_metadata("adapter_tool")
        assert meta is not None
        assert meta.category == "adapter"
        record = await tool_runtime.execute("adapter_tool", parameters={"x": 1})
        assert record.success is True
        assert "adapter tool ran" in record.output_preview

    async def test_single_active_per_pipeline_subsystem(self) -> None:
        pipeline = build_intelligent_pipeline()
        registry = AdapterRegistry(pipeline)
        first = registry.register("memory", "first", _RecordingMemoryAdapter())
        second = registry.register("memory", "second", _RecordingMemoryAdapter())
        registry.activate("memory", "first")
        registry.activate("memory", "second")
        assert first.active is False
        assert second.active is True

    async def test_provider_activation_refused(self) -> None:
        registry = AdapterRegistry(build_intelligent_pipeline())
        registry.register("provider", "fake", _ProviderAdapter())
        with pytest.raises(AdapterActivationUnsupported):
            registry.activate("provider", "fake")

    async def test_unknown_adapter_activation_raises(self) -> None:
        registry = AdapterRegistry(build_intelligent_pipeline())
        with pytest.raises(KeyError):
            registry.activate("memory", "ghost")

    async def test_tool_activation_without_runtime_raises(self) -> None:
        registry = AdapterRegistry(build_intelligent_pipeline())
        registry.register("tool", "orphan", _AsyncToolAdapter())
        with pytest.raises(RuntimeError):
            registry.activate("tool", "orphan")


class TestUseSubsystem:
    def test_unknown_subsystem_rejected(self) -> None:
        pipeline = build_intelligent_pipeline()
        with pytest.raises(ValueError, match="Unknown subsystem"):
            pipeline.use_subsystem("hyperdrive", object())


# ===========================================================================
# API
# ===========================================================================


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    import config.settings as settings_module

    original = settings_module.get_settings
    settings_module.get_settings = lambda: settings_module.Settings(
        anthropic_api_key=None,
        default_model_provider="anthropic",
    )
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    settings_module.get_settings = original
    get_settings.cache_clear()


class TestAdaptersAPI:
    def test_categories_describe_real_interfaces(self, client: TestClient) -> None:
        data = client.get("/api/v1/adapters/categories").json()
        assert set(data) == {"memory", "context", "router", "tool", "provider", "plugin"}
        memory_methods = {m["name"] for m in data["memory"]["required_methods"]}
        assert {"store", "retrieve_relevant", "get_stats", "clear"} == memory_methods
        assert data["provider"]["runtime_activatable"] is False
        assert data["tool"]["runtime_activatable"] is True

    def test_empty_listing_on_boot(self, client: TestClient) -> None:
        assert client.get("/api/v1/adapters").json()["count"] == 0

    def test_activation_flow_via_api(self, client: TestClient) -> None:
        # Register in Python (adapters are objects), activate via API.
        registry = client.app.state.adapter_registry
        registry.register("memory", "api_recorder", _RecordingMemoryAdapter())

        listing = client.get("/api/v1/adapters?category=memory").json()
        assert listing["count"] == 1
        resp = client.post("/api/v1/adapters/memory/api_recorder/activate")
        assert resp.status_code == 200
        assert resp.json()["active"] is True

    def test_activate_unknown_404(self, client: TestClient) -> None:
        assert (
            client.post("/api/v1/adapters/memory/ghost/activate").status_code == 404
        )

    def test_activate_provider_409(self, client: TestClient) -> None:
        client.app.state.adapter_registry.register(
            "provider", "fake", _ProviderAdapter()
        )
        resp = client.post("/api/v1/adapters/provider/fake/activate")
        assert resp.status_code == 409
