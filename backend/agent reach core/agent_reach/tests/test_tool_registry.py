"""Unit tests for ToolRegistry (M6.4)."""

from __future__ import annotations

from typing import Any

import pytest

from infrastructure.tool_manager import ToolManager
from infrastructure.tool_registry import ToolMetadata, ToolRegistry


async def _add(a: int = 0, b: int = 0) -> int:
    return a + b


async def _greet(name: str = "world") -> str:
    return f"hello, {name}"


async def _boom() -> None:
    raise RuntimeError("tool boom")


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_returns_metadata(self, registry: ToolRegistry) -> None:
        meta = registry.register("add", _add, description="Add numbers")
        assert meta.name == "add"
        assert meta.description == "Add numbers"
        assert meta.version == "1.0.0"
        assert meta.enabled is True
        assert meta.tool_id

    def test_register_with_full_metadata(self, registry: ToolRegistry) -> None:
        meta = registry.register(
            "add",
            _add,
            description="Add two numbers",
            version="2.1.0",
            category="math",
            tags=["arithmetic", "basic"],
            allowed_agents=frozenset({"coding"}),
        )
        assert meta.version == "2.1.0"
        assert meta.category == "math"
        assert meta.tags == ["arithmetic", "basic"]
        assert meta.allowed_agents == frozenset({"coding"})

    def test_register_preserves_tool_id_on_update(self, registry: ToolRegistry) -> None:
        meta1 = registry.register("add", _add, version="1.0.0")
        tool_id = meta1.tool_id
        meta2 = registry.register("add", _add, version="2.0.0")
        assert meta2.tool_id == tool_id
        assert meta2.version == "2.0.0"

    def test_register_disabled(self, registry: ToolRegistry) -> None:
        meta = registry.register("add", _add, enabled=False)
        assert meta.enabled is False

    def test_unregister(self, registry: ToolRegistry) -> None:
        registry.register("add", _add)
        assert registry.unregister("add") is True
        assert registry.get_metadata("add") is None

    def test_unregister_missing(self, registry: ToolRegistry) -> None:
        assert registry.unregister("ghost") is False


# ---------------------------------------------------------------------------
# Enable / disable
# ---------------------------------------------------------------------------


class TestEnableDisable:
    def test_enable(self, registry: ToolRegistry) -> None:
        registry.register("add", _add, enabled=False)
        assert registry.enable("add") is True
        assert registry.is_enabled("add") is True

    def test_disable(self, registry: ToolRegistry) -> None:
        registry.register("add", _add)
        assert registry.disable("add") is True
        assert registry.is_enabled("add") is False

    def test_enable_missing(self, registry: ToolRegistry) -> None:
        assert registry.enable("ghost") is False

    def test_disable_missing(self, registry: ToolRegistry) -> None:
        assert registry.disable("ghost") is False

    def test_is_enabled_missing(self, registry: ToolRegistry) -> None:
        assert registry.is_enabled("ghost") is False


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class TestExecution:
    async def test_call_enabled_tool(self, registry: ToolRegistry) -> None:
        registry.register("add", _add)
        result = await registry.call("add", "coding", a=2, b=3)
        assert result == 5

    async def test_call_disabled_tool_raises(self, registry: ToolRegistry) -> None:
        registry.register("add", _add, enabled=False)
        with pytest.raises(KeyError, match="disabled"):
            await registry.call("add", "coding")

    async def test_call_unregistered_tool_raises(self, registry: ToolRegistry) -> None:
        with pytest.raises(KeyError, match="not registered"):
            await registry.call("ghost", "coding")

    async def test_call_permission_denied(self, registry: ToolRegistry) -> None:
        registry.register(
            "add", _add, allowed_agents=frozenset({"coding"})
        )
        with pytest.raises(PermissionError):
            await registry.call("add", "research")

    async def test_call_increments_count(self, registry: ToolRegistry) -> None:
        registry.register("add", _add)
        await registry.call("add", "coding", a=1, b=1)
        await registry.call("add", "coding", a=2, b=2)
        meta = registry.get_metadata("add")
        assert meta.call_count == 2


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_get_metadata(self, registry: ToolRegistry) -> None:
        registry.register("add", _add, description="Add")
        meta = registry.get_metadata("add")
        assert meta is not None
        assert meta.name == "add"

    def test_get_metadata_missing(self, registry: ToolRegistry) -> None:
        assert registry.get_metadata("ghost") is None

    def test_list_tools_empty(self, registry: ToolRegistry) -> None:
        assert registry.list_tools() == []

    def test_list_tools_all(self, registry: ToolRegistry) -> None:
        registry.register("add", _add)
        registry.register("greet", _greet)
        names = [m.name for m in registry.list_tools()]
        assert names == ["add", "greet"]

    def test_list_tools_enabled_only(self, registry: ToolRegistry) -> None:
        registry.register("add", _add, enabled=True)
        registry.register("greet", _greet, enabled=False)
        names = [m.name for m in registry.list_tools(enabled_only=True)]
        assert names == ["add"]

    def test_list_tools_by_category(self, registry: ToolRegistry) -> None:
        registry.register("add", _add, category="math")
        registry.register("greet", _greet, category="text")
        names = [m.name for m in registry.list_tools(category="math")]
        assert names == ["add"]

    def test_list_tools_by_tag(self, registry: ToolRegistry) -> None:
        registry.register("add", _add, tags=["arithmetic"])
        registry.register("greet", _greet, tags=["text"])
        names = [m.name for m in registry.list_tools(tag="arithmetic")]
        assert names == ["add"]

    def test_list_categories(self, registry: ToolRegistry) -> None:
        registry.register("add", _add, category="math")
        registry.register("greet", _greet, category="text")
        registry.register("other", _greet)  # uncategorized
        cats = registry.list_categories()
        assert "math" in cats
        assert "text" in cats
        assert "uncategorized" in cats

    def test_list_tags(self, registry: ToolRegistry) -> None:
        registry.register("add", _add, tags=["a", "b"])
        registry.register("greet", _greet, tags=["b", "c"])
        assert registry.list_tags() == ["a", "b", "c"]

    def test_search_by_name(self, registry: ToolRegistry) -> None:
        registry.register("add", _add)
        registry.register("greet", _greet)
        results = registry.search("add")
        assert [m.name for m in results] == ["add"]

    def test_search_by_description(self, registry: ToolRegistry) -> None:
        registry.register("add", _add, description="Adds two numbers")
        results = registry.search("numbers")
        assert [m.name for m in results] == ["add"]

    def test_search_by_tag(self, registry: ToolRegistry) -> None:
        registry.register("add", _add, tags=["arithmetic"])
        results = registry.search("arithmetic")
        assert [m.name for m in results] == ["add"]

    def test_search_case_insensitive(self, registry: ToolRegistry) -> None:
        registry.register("add", _add, description="ADD numbers")
        results = registry.search("add")
        assert [m.name for m in results] == ["add"]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_get_stats_empty(self, registry: ToolRegistry) -> None:
        stats = registry.get_stats()
        assert stats == {
            "total": 0,
            "enabled": 0,
            "disabled": 0,
            "categories": 0,
            "total_calls": 0,
        }

    def test_get_stats_populated(self, registry: ToolRegistry) -> None:
        registry.register("add", _add, category="math", enabled=True)
        registry.register("greet", _greet, category="text", enabled=False)
        stats = registry.get_stats()
        assert stats["total"] == 2
        assert stats["enabled"] == 1
        assert stats["disabled"] == 1
        assert stats["categories"] == 2


# ---------------------------------------------------------------------------
# Metadata serialization
# ---------------------------------------------------------------------------


class TestMetadataSerialization:
    def test_to_dict(self, registry: ToolRegistry) -> None:
        registry.register(
            "add",
            _add,
            description="Add",
            version="1.2.3",
            category="math",
            tags=["a"],
        )
        meta = registry.get_metadata("add")
        d = meta.to_dict()
        assert d["name"] == "add"
        assert d["version"] == "1.2.3"
        assert d["category"] == "math"
        assert d["tags"] == ["a"]
        assert d["enabled"] is True
        assert d["call_count"] == 0


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear(self, registry: ToolRegistry) -> None:
        registry.register("add", _add)
        registry.register("greet", _greet)
        registry.clear()
        assert registry.list_tools() == []
        assert registry.get_metadata("add") is None


# ---------------------------------------------------------------------------
# Underlying manager injection
# ---------------------------------------------------------------------------


class TestManagerInjection:
    def test_custom_manager_injected(self) -> None:
        manager = ToolManager()
        registry = ToolRegistry(manager=manager)
        registry.register("add", _add)
        meta = registry.get_metadata("add")
        assert meta is not None
        assert meta.name == "add"
