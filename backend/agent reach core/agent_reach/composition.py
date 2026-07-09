"""
Composition root: the one place concrete implementations are wired
into the abstractions core/ depends on.
"""

from __future__ import annotations

import logging
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
from core.intelligent_pipeline import IntelligentPipeline, PipelineConfig
from core.planner import RuleBasedPlanner
from domain.interfaces import Agent, ModelClient
from domain.models import AgentType
from infrastructure.model_client import AnthropicModelClient
from infrastructure.provider_manager import ProviderManager, SUPPORTED_PROVIDERS
from workflows.engine import WorkflowEngine
from workflows.orchestration import AgentOrchestrator, ToolOrchestrator
from workflows.registry import WorkflowRegistry

logger = logging.getLogger(__name__)


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
    agents: list[Agent] = [ResearchAgent(model_client=model_client), CodingAgent(model_client=model_client)]
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
    model_client = build_provider_manager(settings)

    plugin_manager = _try_load_plugins()

    dispatcher = AgentDispatcher(
        agents=build_default_agent_registry(model_client, plugin_manager),
        retry_policy=settings.to_retry_policy(),
    )
    return MainController(planner=RuleBasedPlanner(), dispatcher=dispatcher)


def build_provider_manager(settings: Optional[Settings] = None) -> ProviderManager:
    """Build the multi-provider routing manager (M6.3 / M9 production).

    Collects every configured API key from Settings and wires them into a
    single ProviderManager. The manager implements ModelClient, so it
    drops into the same slot the old single-provider client occupied.

    When no provider has an API key configured, the manager responds to
    every ``complete()`` call with a clear error message telling the user
    exactly which environment variables to set — no silent mock fallback.
    """
    settings = settings or get_settings()

    provider_keys: dict[str, Optional[str]] = {}
    for provider in SUPPORTED_PROVIDERS:
        key = settings.provider_api_key(provider)
        provider_keys[provider] = key

    configured = [p for p, k in provider_keys.items() if k]
    if not configured:
        logger.warning(
            "No provider API key configured — the runtime will respond with "
            "clear error messages naming the required environment variables. "
            "Set at least one of: %s",
            ", ".join(f"{p.upper()}_API_KEY" for p in SUPPORTED_PROVIDERS),
        )

    manager = ProviderManager(
        provider_keys=provider_keys,
        default_provider=settings.default_model_provider,
    )
    if settings.default_model:
        manager.set_model(settings.default_model_provider, settings.default_model)

    logger.info(
        "ProviderManager initialised: %d/%d providers configured (%s)",
        len(configured),
        len(SUPPORTED_PROVIDERS),
        ", ".join(configured) if configured else "none",
    )
    return manager
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


def build_tool_runtime(
    settings: Optional[Settings] = None,
) -> "ToolRuntime":
    """Build the M9.6 Live Tool Runtime.

    Reuses the existing ToolRegistry (M6.4) and registers the
    production tool implementations (infrastructure/production_tools).
    The runtime adds execution history, retries, and metrics on top —
    it does not replace the registry or the M3 ToolExecutor.
    """
    from core.tool_runtime import ToolRuntime
    from infrastructure.production_tools import register_production_tools
    from infrastructure.tool_registry import ToolRegistry

    settings = settings or get_settings()
    registry = ToolRegistry()
    register_production_tools(registry)
    return ToolRuntime(
        registry,
        default_timeout_seconds=settings.task_timeout_seconds,
    )



def build_intelligent_pipeline(
    settings: Optional[Settings] = None,
    config: Optional[PipelineConfig] = None,
    event_hub: Optional[Any] = None,
) -> IntelligentPipeline:
    """Build the fully integrated M7.5 Intelligent Pipeline.

    This is the recommended entry point for all user requests.
    It wraps MainController and layers every M7 subsystem around it:
    Router → Memory → Context → MOA → Planner → Agents → Reflection
    → Knowledge Graph → Learning → Tutti.

    Falls back gracefully to bare MainController behavior when
    subsystems are disabled in PipelineConfig.

    M9.24: pass an event_hub (core/runtime_events.RuntimeEventHub) to
    have every execution publish the canonical runtime event chain.
    """
    controller = build_default_controller(settings)
    return IntelligentPipeline(
        controller=controller, config=config, event_hub=event_hub
    )


def build_event_hub() -> "RuntimeEventHub":
    """Build the M9.24 runtime event hub around the existing EventBus."""
    from core.runtime_events import RuntimeEventHub

    return RuntimeEventHub()


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
