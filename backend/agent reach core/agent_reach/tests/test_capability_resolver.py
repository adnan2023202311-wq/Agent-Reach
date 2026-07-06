"""Tests for Capability Resolver (M4.3)."""

from __future__ import annotations

import pytest

from core.capability_resolver import CapabilityResolver, ResolvedCapability


async def _dummy_executor(x: int) -> int:
    return x * 2


async def _fallback_executor(x: int) -> int:
    return x + 1


class TestCapabilityResolver:
    def test_register_and_resolve(self) -> None:
        resolver = CapabilityResolver()
        resolver.register("double", _dummy_executor)
        resolved = resolver.resolve("double")
        assert resolved is not None
        assert resolved.capability_id == "double"
        assert resolved.executor is _dummy_executor
        assert resolved.fallback is False

    def test_resolve_missing_returns_none(self) -> None:
        resolver = CapabilityResolver()
        assert resolver.resolve("missing") is None

    def test_has_capability(self) -> None:
        resolver = CapabilityResolver()
        resolver.register("exists", _dummy_executor)
        assert resolver.has_capability("exists") is True
        assert resolver.has_capability("missing") is False

    def test_fallback_resolution(self) -> None:
        resolver = CapabilityResolver()
        resolver.register("primary", _dummy_executor)
        resolver.register("fallback", _fallback_executor)
        resolver.set_fallback("missing", "fallback")
        resolved = resolver.resolve("missing")
        assert resolved is not None
        assert resolved.capability_id == "missing"
        assert resolved.executor is _fallback_executor
        assert resolved.fallback is True

    def test_fallback_chain_missing(self) -> None:
        resolver = CapabilityResolver()
        resolver.set_fallback("a", "b")
        assert resolver.resolve("a") is None

    def test_unregister(self) -> None:
        resolver = CapabilityResolver()
        resolver.register("tmp", _dummy_executor)
        assert resolver.has_capability("tmp") is True
        assert resolver.unregister("tmp") is True
        assert resolver.has_capability("tmp") is False
        assert resolver.unregister("tmp") is False

    def test_list_capabilities(self) -> None:
        resolver = CapabilityResolver()
        resolver.register("a", _dummy_executor)
        resolver.register("b", _fallback_executor)
        assert sorted(resolver.list_capabilities()) == ["a", "b"]

    def test_metadata(self) -> None:
        resolver = CapabilityResolver()
        resolver.register("tool", _dummy_executor, {"category": "math"})
        assert resolver.get_metadata("tool") == {"category": "math"}
        assert resolver.resolve("tool").metadata == {"category": "math"}

    def test_clear(self) -> None:
        resolver = CapabilityResolver()
        resolver.register("a", _dummy_executor)
        resolver.clear()
        assert resolver.list_capabilities() == []
        assert resolver.resolve("a") is None

    @pytest.mark.asyncio
    async def test_executor_is_callable(self) -> None:
        resolver = CapabilityResolver()
        resolver.register("double", _dummy_executor)
        resolved = resolver.resolve("double")
        result = await resolved.executor(5)
        assert result == 10
