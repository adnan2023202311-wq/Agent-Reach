"""Tests for Skill Engine (M4.5)."""

from __future__ import annotations

import pytest

from skills.engine import Skill, SkillEngine, SkillRegistry


async def _greet_skill(name: str = "world") -> str:
    return f"Hello, {name}!"


async def _fail_skill() -> None:
    raise RuntimeError("boom")


class TestSkillRegistry:
    def test_register_and_get(self) -> None:
        registry = SkillRegistry()
        skill = Skill(id="greet", name="Greeting", executor=_greet_skill)
        registry.register(skill)
        assert registry.get("greet") is skill

    def test_unregister(self) -> None:
        registry = SkillRegistry()
        registry.register(Skill(id="x", executor=_greet_skill))
        assert registry.unregister("x") is True
        assert registry.get("x") is None
        assert registry.unregister("x") is False

    def test_list_skills(self) -> None:
        registry = SkillRegistry()
        registry.register(Skill(id="a", executor=_greet_skill))
        registry.register(Skill(id="b", executor=_greet_skill))
        assert len(registry.list_skills()) == 2

    def test_find_by_name(self) -> None:
        registry = SkillRegistry()
        registry.register(Skill(id="a", name="search", executor=_greet_skill))
        registry.register(Skill(id="b", name="other", executor=_greet_skill))
        found = registry.find_by_name("search")
        assert len(found) == 1
        assert found[0].id == "a"

    def test_clear(self) -> None:
        registry = SkillRegistry()
        registry.register(Skill(id="a", executor=_greet_skill))
        registry.clear()
        assert registry.list_skills() == []


class TestSkillEngine:
    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        engine = SkillEngine()
        engine.registry.register(Skill(id="greet", executor=_greet_skill))
        result = await engine.execute("greet", {"name": "Agent"})
        assert result.success is True
        assert result.output == "Hello, Agent!"
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_not_found(self) -> None:
        engine = SkillEngine()
        result = await engine.execute("missing")
        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_failure_isolated(self) -> None:
        engine = SkillEngine()
        engine.registry.register(Skill(id="fail", executor=_fail_skill))
        result = await engine.execute("fail")
        assert result.success is False
        assert "boom" in result.error

    @pytest.mark.asyncio
    async def test_execute_batch(self) -> None:
        engine = SkillEngine()
        engine.registry.register(Skill(id="greet", executor=_greet_skill))
        engine.registry.register(Skill(id="fail", executor=_fail_skill))
        results = await engine.execute_batch(
            [("greet", {"name": "A"}), ("fail", None), ("missing", None)]
        )
        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is False

    def test_skill_metadata(self) -> None:
        skill = Skill(
            id="meta",
            name="Meta",
            version="2.0.0",
            metadata={"category": "test"},
        )
        assert skill.version == "2.0.0"
        assert skill.metadata["category"] == "test"
