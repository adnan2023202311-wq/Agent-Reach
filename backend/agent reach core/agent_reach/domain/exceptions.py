"""
Domain layer: error types.

Layer: Domain (innermost).

Exceptions live here rather than in core/ for the same reason
interfaces do: they define a contract ("this is what can go wrong")
that agents, planners, and the dispatcher all need to raise or catch,
without any of them depending on the orchestration package. The API
layer (api/exception_handlers.py) catches this single hierarchy and
maps it to HTTP responses, so nothing internal needs to know it's
being served over HTTP.
"""

from __future__ import annotations


class AgentReachError(Exception):
    """Base class for every error raised inside Agent Reach."""


class PlanningError(AgentReachError):
    """A Planner could not produce a valid TaskPlan for a request."""


class AgentNotRegisteredError(AgentReachError):
    """A SubTask asked for an AgentType with no registered implementation.

    This is a configuration/deployment bug (an agent that should have
    been wired in the composition root wasn't), not a transient task
    failure — it is raised immediately rather than retried.
    """

    def __init__(self, agent_type: str) -> None:
        self.agent_type = agent_type
        super().__init__(f"No agent registered for type '{agent_type}'")


class AgentExecutionError(AgentReachError):
    """An agent kept failing after AgentDispatcher exhausted its retry budget."""

    def __init__(self, agent_type: str, subtask_id: str, original_error: BaseException) -> None:
        self.agent_type = agent_type
        self.subtask_id = subtask_id
        self.original_error = original_error
        super().__init__(
            f"Agent '{agent_type}' failed on subtask {subtask_id} "
            f"after all retries: {original_error}"
        )


class ConfigurationError(AgentReachError):
    """Required configuration is missing or invalid at startup."""


class ModelProviderError(AgentReachError):
    """A call to a model provider (Anthropic, OpenAI, ...) failed.

    Same wrapping pattern as AgentExecutionError: whatever the
    provider SDK actually raised (a rate limit, an auth failure, a
    connection drop) is captured in `original_error`, but callers only
    ever need to know about this one type. An Agent implementation
    that calls a ModelClient can let this propagate — AgentDispatcher
    already retries any exception a subtask raises.
    """

    def __init__(self, provider: str, original_error: BaseException) -> None:
        self.provider = provider
        self.original_error = original_error
        super().__init__(f"Model provider '{provider}' call failed: {original_error}")
