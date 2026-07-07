"""Unit tests for AgentRegistry (M6.5)."""

from __future__ import annotations

from typing import Any

import pytest

from agents.agent_registry import AgentMetadata, AgentRegistry
from domain.interfaces import Agent
from domain.models import AgentType, SubTask


class EchoAgent(Agent):
    """Fake agent for tests."""

    def __init__(self, agent_type: AgentType) -> None:
        self._agent_type = agent_type

    @property
    def agent_type(self) -> AgentType:
        return self._agent_type

    async def execute(self, subtask: SubTask) -> Any:
        return f"echo:{subtask.description}"


@pytest.fixture
def registry() -> AgentRegistry:
    return AgentRegistry()


@pytest.fixture
def research_agent() -> Agent:
    return EchoAgent(AgentType.RESEARCH)


@pytest.fixture
def coding_agent() -> Agent:
    return EchoAgent(AgentType.CODING)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_returns_metadata(
        self, registry: AgentRegistry, research_agent: Agent
    ) -> None:
        meta = registry.register(research_agent, description="Does research")
        assert meta.agent_type is AgentType.RESEARCH
        assert meta.description == "Does research"
        assert meta.version == "1.0.0"
        assert meta.enabled is True
        assert meta.agent_id

    def test_register_with_full_metadata(
        self, registry: AgentRegistry, research_agent: Agent
    ) -> None:
        meta = registry.register(
            research_agent,
            name="Research Pro",
            description="Advanced research",
            version="2.0.0",
            dependencies=["providers:anthropic", "tools:web_search"],
            tags=["research", "web"],
        )
        assert meta.name == "Research Pro"
        assert meta.version == "2.0.0"
        assert meta.dependencies == ["providers:anthropic", "tools:web_search"]
        assert meta.tags == ["research", "web"]

    def test_register_preserves_id_on_update(
        self, registry: AgentRegistry, research_agent: Agent
    ) -> None:
        meta1 = registry.register(research_agent, version="1.0.0")
        agent_id = meta1.agent_id
        meta2 = registry.register(research_agent, version="2.0.0")
        assert meta2.agent_id == agent_id
        assert meta2.version == "2.0.0"

    def test_register_disabled(
        self, registry: AgentRegistry, research_agent: Agent
    ) -> None:
        meta = registry.register(research_agent, enabled=False)
        assert meta.enabled is False

    def test_unregister(
        self, registry: AgentRegistry, research_agent: Agent
    ) -> None:
        registry.register(research_agent)
        assert registry.unregister(AgentType.RESEARCH) is True
        assert registry.get_agent(AgentType.RESEARCH) is None

    def test_unregister_missing(self, registry: AgentRegistry) -> None:
        assert registry.unregister(AgentType.RESEARCH) is False

    def test_register_with_initial_agents(self) -> None:
        initial = {
            AgentType.RESEARCH: EchoAgent(AgentType.RESEARCH),
            AgentType.CODING: EchoAgent(AgentType.CODING),
        }
        reg = AgentRegistry(initial_agents=initial)
        assert reg.get_agent(AgentType.RESEARCH) is not None
        assert reg.get_agent(AgentType.CODING) is not None


# ---------------------------------------------------------------------------
# Enable / disable
# ---------------------------------------------------------------------------


class TestEnableDisable:
    def test_enable(
        self, registry: AgentRegistry, research_agent: Agent
    ) -> None:
        registry.register(research_agent, enabled=False)
        assert registry.enable(AgentType.RESEARCH) is True
        assert registry.is_enabled(AgentType.RESEARCH) is True

    def test_disable(
        self, registry: AgentRegistry, research_agent: Agent
    ) -> None:
        registry.register(research_agent)
        assert registry.disable(AgentType.RESEARCH) is True
        assert registry.is_enabled(AgentType.RESEARCH) is False

    def test_enable_missing(self, registry: AgentRegistry) -> None:
        assert registry.enable(AgentType.RESEARCH) is False

    def test_disable_missing(self, registry: AgentRegistry) -> None:
        assert registry.disable(AgentType.RESEARCH) is False


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------


class TestAccess:
    def test_get_agent(
        self, registry: AgentRegistry, research_agent: Agent
    ) -> None:
        registry.register(research_agent)
        assert registry.get_agent(AgentType.RESEARCH) is research_agent

    def test_get_agent_missing(self, registry: AgentRegistry) -> None:
        assert registry.get_agent(AgentType.RESEARCH) is None

    def test_get_metadata(
        self, registry: AgentRegistry, research_agent: Agent
    ) -> None:
        registry.register(research_agent, description="Research")
        meta = registry.get_metadata(AgentType.RESEARCH)
        assert meta is not None
        assert meta.description == "Research"

    def test_get_metadata_missing(self, registry: AgentRegistry) -> None:
        assert registry.get_metadata(AgentType.RESEARCH) is None

    def test_get_enabled_agents(
        self,
        registry: AgentRegistry,
        research_agent: Agent,
        coding_agent: Agent,
    ) -> None:
        registry.register(research_agent, enabled=True)
        registry.register(coding_agent, enabled=False)
        enabled = registry.get_enabled_agents()
        assert AgentType.RESEARCH in enabled
        assert AgentType.CODING not in enabled

    def test_list_metadata(
        self,
        registry: AgentRegistry,
        research_agent: Agent,
        coding_agent: Agent,
    ) -> None:
        registry.register(research_agent, tags=["research"])
        registry.register(coding_agent, tags=["code"])
        all_meta = registry.list_metadata()
        assert len(all_meta) == 2

    def test_list_metadata_enabled_only(
        self,
        registry: AgentRegistry,
        research_agent: Agent,
        coding_agent: Agent,
    ) -> None:
        registry.register(research_agent, enabled=True)
        registry.register(coding_agent, enabled=False)
        enabled = registry.list_metadata(enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0].agent_type is AgentType.RESEARCH

    def test_list_metadata_by_tag(
        self,
        registry: AgentRegistry,
        research_agent: Agent,
        coding_agent: Agent,
    ) -> None:
        registry.register(research_agent, tags=["research"])
        registry.register(coding_agent, tags=["code"])
        results = registry.list_metadata(tag="research")
        assert len(results) == 1
        assert results[0].agent_type is AgentType.RESEARCH


# ---------------------------------------------------------------------------
# Dependency validation
# ---------------------------------------------------------------------------


class TestDependencyValidation:
    def test_validate_dependencies_all_met(
        self, registry: AgentRegistry, research_agent: Agent
    ) -> None:
        registry.set_dependency_providers(
            "providers", {"anthropic", "openai"}
        )
        registry.set_dependency_providers("tools", {"web_search"})
        registry.register(
            research_agent,
            dependencies=["providers:anthropic", "tools:web_search"],
        )
        missing = registry.validate_dependencies(AgentType.RESEARCH)
        assert missing == []

    def test_validate_dependencies_missing(
        self, registry: AgentRegistry, research_agent: Agent
    ) -> None:
        registry.set_dependency_providers("providers", {"anthropic"})
        registry.register(
            research_agent,
            dependencies=["providers:anthropic", "tools:web_search"],
        )
        missing = registry.validate_dependencies(AgentType.RESEARCH)
        assert missing == ["tools:web_search"]

    def test_validate_dependencies_no_category_prefix(
        self, registry: AgentRegistry, research_agent: Agent
    ) -> None:
        registry.set_dependency_providers("tools", {"web_search"})
        registry.register(research_agent, dependencies=["web_search"])
        missing = registry.validate_dependencies(AgentType.RESEARCH)
        assert missing == []

    def test_validate_dependencies_no_category_prefix_missing(
        self, registry: AgentRegistry, research_agent: Agent
    ) -> None:
        registry.set_dependency_providers("tools", {"other_tool"})
        registry.register(research_agent, dependencies=["web_search"])
        missing = registry.validate_dependencies(AgentType.RESEARCH)
        assert missing == ["web_search"]

    def test_validate_all(
        self,
        registry: AgentRegistry,
        research_agent: Agent,
        coding_agent: Agent,
    ) -> None:
        registry.set_dependency_providers("providers", {"anthropic"})
        registry.register(
            research_agent, dependencies=["providers:anthropic"]
        )
        registry.register(coding_agent, dependencies=["providers:openai"])
        issues = registry.validate_all()
        assert AgentType.RESEARCH not in issues
        assert AgentType.CODING in issues

    def test_add_dependency_provider(
        self, registry: AgentRegistry
    ) -> None:
        registry.add_dependency_provider("tools", "git_clone")
        assert "git_clone" in registry._dependency_providers["tools"]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_get_stats_empty(self, registry: AgentRegistry) -> None:
        stats = registry.get_stats()
        assert stats == {"total": 0, "enabled": 0, "disabled": 0}

    def test_get_stats_populated(
        self,
        registry: AgentRegistry,
        research_agent: Agent,
        coding_agent: Agent,
    ) -> None:
        registry.register(research_agent, enabled=True)
        registry.register(coding_agent, enabled=False)
        stats = registry.get_stats()
        assert stats["total"] == 2
        assert stats["enabled"] == 1
        assert stats["disabled"] == 1


# ---------------------------------------------------------------------------
# Metadata serialization
# ---------------------------------------------------------------------------


class TestMetadataSerialization:
    def test_to_dict(
        self, registry: AgentRegistry, research_agent: Agent
    ) -> None:
        registry.register(
            research_agent,
            name="Research",
            description="Does research",
            version="1.2.3",
            dependencies=["providers:anthropic"],
            tags=["research"],
        )
        meta = registry.get_metadata(AgentType.RESEARCH)
        d = meta.to_dict()
        assert d["agent_type"] == "research"
        assert d["name"] == "Research"
        assert d["version"] == "1.2.3"
        assert d["dependencies"] == ["providers:anthropic"]
        assert d["tags"] == ["research"]
        assert d["enabled"] is True


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear(
        self,
        registry: AgentRegistry,
        research_agent: Agent,
        coding_agent: Agent,
    ) -> None:
        registry.register(research_agent)
        registry.register(coding_agent)
        registry.clear()
        assert registry.get_agent(AgentType.RESEARCH) is None
        assert registry.get_agent(AgentType.CODING) is None
        assert registry.list_metadata() == []
