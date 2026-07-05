"""
Domain layer: ports (abstract interfaces).

Layer: Domain (innermost).

Three interfaces live here: Agent, Planner, and ModelClient. Each is
justified by a concrete, present-tense need, not a speculative one:

- Agent: AgentDispatcher already routes to two implementations
  (ResearchAgent, CodingAgent), with seven more planned (Blueprint
  Section 9).
- Planner: one implementation today (RuleBasedPlanner), but
  MainController already depends on the interface, and swapping in an
  LLM-driven planner is a near-term milestone.
- ModelClient: zero implementations wired into an agent yet, but every
  agent that does real work will need to call a model, and the
  Blueprint (Section 19) explicitly plans multiple providers (OpenAI,
  Anthropic, Google, DeepSeek, Groq, OpenRouter, ...). Without this
  seam, the first agent to go from stub to real would hardcode a
  provider SDK directly into itself, and every agent after it would
  repeat that — the exact duplication this interface exists to avoid.

A MemoryStore interface was deliberately NOT added here. There is
exactly one implementation (infrastructure/memory_store.py) and zero
callers of it — an interface with one implementation and no consumer
is speculation, not abstraction. Add it back the moment a second
implementation (e.g. SQLite-backed) needs to be swappable with it.

Likewise, this file does NOT define a "ModelRouter" that selects among
multiple ModelClients by cost/speed/capability (Blueprint Section 19's
full vision). That's meaningful once 2+ ModelClient implementations
exist to route between; with one (Anthropic), it would be a router
with a single hardcoded destination — an abstraction with nothing to
abstract over yet.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from domain.models import AgentType, SubTask, TaskPlan


class Agent(ABC):
    """Contract every specialized agent (Blueprint Section 9) must implement.

    Implementations live in agents/ and are registered with
    AgentDispatcher in composition.py — never imported directly by core/.
    """

    @property
    @abstractmethod
    def agent_type(self) -> AgentType:
        """Which AgentType this instance handles."""

    @abstractmethod
    async def execute(self, subtask: SubTask) -> Any:
        """Run the subtask and return a JSON-serializable result, or raise.

        Raising is the expected failure signal — AgentDispatcher owns
        all retry/timeout/error-wrapping logic, so implementations
        should not catch-and-suppress their own errors.
        """


class Planner(ABC):
    """Contract for turning a raw user request into a TaskPlan."""

    @abstractmethod
    async def create_plan(self, request: str) -> TaskPlan:
        """Decompose `request` into an ordered TaskPlan."""


class ModelClient(ABC):
    """Contract for calling one LLM provider (Blueprint Section 19).

    Deliberately narrow: text messages in, text out. No tool-use, no
    streaming, no multi-provider routing. Those are real needs, but
    not yet — tool-use belongs to the Execution Engine milestone that
    depends on this one; routing belongs to the milestone after a
    second provider actually exists. Widening this interface before
    either is needed would mean guessing at a shape instead of letting
    the next concrete requirement define it.
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        """Send `messages` to the model and return the text of its reply.

        Raises:
            domain.exceptions.ModelProviderError: on any failure
                (auth, rate limit, network, malformed response) — the
                specific provider SDK's exception types never leak
                past this boundary.
        """
