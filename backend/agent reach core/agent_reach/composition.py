"""
Composition root: the one place concrete implementations are wired
into the abstractions core/ depends on.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from agents.coding_agent import CodingAgent
from agents.plugin_agent import PluginAgent, build_plugin_manager
from agents.research_agent import ResearchAgent
from config.settings import Settings, get_settings
from conversation.engine import ConversationEngine
from conversation.session_manager import SessionManager
from core.controller import MainController
from core.dispatcher import AgentDispatcher
from core.planner import RuleBasedPlanner
from domain.interfaces import Agent, ModelClient
from domain.models import AgentType
from infrastructure.model_client import AnthropicModelClient
from workflows.engine import WorkflowEngine
from workflows.orchestration import AgentOrchestrator, ToolOrchestrator
from workflows.registry import WorkflowRegistry


def build_default_agent_registry(
    model_client: ModelClient,
    plugin_manager: Optional[Any] = None,
) -> dict[AgentType, Agent]:
    """The out-of-the-box set of agents.

    Milestone 2 addition: if a plugin manager is provided and plugins
    are loaded, they are merged into the registry alongside native
    agents. Native agents take precedence for their AgentType to
    preserve backward compatibility.
    """
    agents: list[Agent] = [ResearchAgent(model_client=model_client), CodingAgent()]
    registry = {agent.agent_type: agent for agent in agents}

    if plugin_manager is not None:
        plugin_agents = _build_plugin_agents(plugin_manager)
        for agent_type, plugin_agent in plugin_agents.items():
            if agent_type not in registry:
                registry[agent_type] = plugin_agent

    return registry


def build_default_controller(settings: Optional[Settings] = None) -> MainController:
    """Wire up a MainController with the default planner, agents, and retry policy.

    Milestone 2 addition: attempts to discover and load plugins from
    AGENT_REACH_PLUGINS_DIR. If the directory doesn't exist or is
    empty, the kernel falls back to the native agent registry.
    """
    settings = settings or get_settings()
    model_client = build_anthropic_model_client(settings)

    plugin_manager = _try_load_plugins()

    dispatcher = AgentDispatcher(
        agents=build_default_agent_registry(model_client, plugin_manager),
        retry_policy=settings.to_retry_policy(),
    )
    return MainController(planner=RuleBasedPlanner(), dispatcher=dispatcher)


def build_anthropic_model_client(settings: Optional[Settings] = None) -> ModelClient:
    """Build the Anthropic ModelClient."""
    settings = settings or get_settings()
    return AnthropicModelClient(
        api_key=settings.provider_api_key(settings.default_model_provider),
        model=settings.default_model,
    )


def build_conversation_engine(
    settings: Optional[Settings] = None,
) -> ConversationEngine:
    """Build a ConversationEngine with its SessionManager and controller."""
    controller = build_default_controller(settings)
    session_manager = SessionManager()
    return ConversationEngine(
        controller=controller,
        session_manager=session_manager,
    )


def build_workflow_engine(
    settings: Optional[Settings] = None,
) -> WorkflowEngine:
    """Build a WorkflowEngine with agent and tool orchestrators."""
    controller = build_default_controller(settings)
    agent_orchestrator = AgentOrchestrator(dispatcher=controller._dispatcher)
    tool_orchestrator = ToolOrchestrator()
    return WorkflowEngine(
        agent_orchestrator=agent_orchestrator,
        tool_orchestrator=tool_orchestrator,
    )


def build_workflow_registry() -> WorkflowRegistry:
    """Build an empty WorkflowRegistry."""
    return WorkflowRegistry()


def _try_load_plugins() -> Optional[Any]:
    """Attempt to discover and load plugins from the filesystem."""
    import asyncio

    from agent_reach.core.plugin.dynamic_loader import DynamicPluginLoader

    plugin_dir = os.environ.get("AGENT_REACH_PLUGINS_DIR", "./plugins")
    if not os.path.exists(plugin_dir):
        return None

    loader = DynamicPluginLoader(plugin_dir)
    plugin_manager = build_plugin_manager(loader)

    try:
        discovered = asyncio.run(loader.discover())
        for plugin_id in discovered:
            asyncio.run(plugin_manager.load(plugin_id))
    except Exception:
        return None

    return plugin_manager


def _build_plugin_agents(plugin_manager: Any) -> dict[AgentType, PluginAgent]:
    """Build PluginAgent instances from loaded plugin capabilities."""
    from agent_reach.core.registry.models import CapabilityType

    agents: dict[AgentType, PluginAgent] = {}
    agent_capabilities = plugin_manager.list_capabilities_by_type(CapabilityType.AGENT)

    for capability in agent_capabilities:
        agent_type = _map_capability_to_agent_type(capability.id)
        if agent_type is not None:
            agents[agent_type] = PluginAgent(
                agent_type=agent_type,
                plugin_id=capability.id,
                plugin_manager=plugin_manager,
            )

    return agents


def _map_capability_to_agent_type(capability_id: str) -> Optional[AgentType]:
    """Map a capability ID to an AgentType."""
    lowered = capability_id.lower()
    mapping = {
        "research": AgentType.RESEARCH,
        "coding": AgentType.CODING,
        "browser": AgentType.BROWSER,
        "news": AgentType.NEWS,
        "writing": AgentType.WRITING,
        "image": AgentType.IMAGE,
        "planning": AgentType.PLANNING,
        "memory": AgentType.MEMORY,
        "social": AgentType.SOCIAL_MEDIA,
    }
    for keyword, agent_type in mapping.items():
        if keyword in lowered:
            return agent_type
    return None
