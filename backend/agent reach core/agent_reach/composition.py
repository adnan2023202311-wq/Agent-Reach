"""
Composition root: the one place concrete implementations are wired
into the abstractions core/ depends on.

This is a single flat module, not a package — it's a handful of small
functions, and a package (with an __init__.py) around them would be a
folder that exists only to hold one file.

Kept separate from api/main.py because they answer different
questions: "what object graph does the app need" (here) vs "how is
that graph exposed over HTTP" (api/main.py). Today api/main.py is the
only caller, so this separation is a bet that a second entrypoint
(a CLI, a worker) shows up later rather than a present-tense need —
flagged here honestly as a judgment call, not a settled requirement.
"""

from __future__ import annotations

from typing import Optional

from agents.coding_agent import CodingAgent
from agents.research_agent import ResearchAgent
from config.settings import Settings, get_settings
from core.controller import MainController
from core.dispatcher import AgentDispatcher
from core.planner import RuleBasedPlanner
from domain.interfaces import Agent, ModelClient
from domain.models import AgentType
from infrastructure.model_client import AnthropicModelClient


def build_default_agent_registry(model_client: ModelClient) -> dict[AgentType, Agent]:
    """The out-of-the-box set of agents. Extend by adding one line here.

    CodingAgent still takes no arguments — it remains a stub. Only
    ResearchAgent is wired to a real ModelClient this milestone (see
    docs/ARCHITECTURE.md, Milestone 5).
    """
    agents: list[Agent] = [ResearchAgent(model_client=model_client), CodingAgent()]
    return {agent.agent_type: agent for agent in agents}


def build_default_controller(settings: Optional[Settings] = None) -> MainController:
    """Wire up a MainController with the default planner, agents, and retry policy.

    Now requires a valid ANTHROPIC_API_KEY to succeed — constructing
    ResearchAgent requires a ModelClient, which requires the key. This
    is intentional fail-fast behavior: a production deployment that's
    missing its provider credentials should refuse to start, not start
    and fail confusingly on the first real request. The test suite is
    unaffected (tests/conftest.py builds its own fakes and never calls
    this function).
    """
    settings = settings or get_settings()
    model_client = build_anthropic_model_client(settings)
    dispatcher = AgentDispatcher(
        agents=build_default_agent_registry(model_client),
        retry_policy=settings.to_retry_policy(),
    )
    return MainController(planner=RuleBasedPlanner(), dispatcher=dispatcher)


def build_anthropic_model_client(settings: Optional[Settings] = None) -> ModelClient:
    """Build the Anthropic ModelClient. Raises ConfigurationError if
    ANTHROPIC_API_KEY isn't set — see build_default_controller above."""
    settings = settings or get_settings()
    return AnthropicModelClient(
        api_key=settings.provider_api_key(settings.default_model_provider),
        model=settings.default_model,
    )
