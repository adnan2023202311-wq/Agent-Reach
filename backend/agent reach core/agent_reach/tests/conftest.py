"""
Shared pytest fixtures.

Uses fake Agent implementations rather than the real ResearchAgent/
CodingAgent stubs — the point of injecting Agent as an abstraction is
that orchestration tests shouldn't care which concrete agent is
plugged in. This is also what makes it possible to unit-test
AgentDispatcher's retry logic deterministically (see
tests/test_dispatcher.py) without waiting on real timeouts.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.controller import MainController
from core.dispatcher import AgentDispatcher
from core.planner import RuleBasedPlanner
from domain.interfaces import Agent
from domain.models import AgentType, RetryPolicy, SubTask


class EchoAgent(Agent):
    """Deterministic fake: returns the subtask description, never fails."""

    def __init__(self, agent_type: AgentType) -> None:
        self._agent_type = agent_type

    @property
    def agent_type(self) -> AgentType:
        return self._agent_type

    async def execute(self, subtask: SubTask) -> Any:
        return f"echo:{subtask.description}"


@pytest.fixture
def fast_retry_policy() -> RetryPolicy:
    # Zero backoff keeps the suite fast even when a test forces retries.
    return RetryPolicy(max_attempts=2, backoff_seconds=0.0, timeout_seconds=1.0)


@pytest.fixture
def dispatcher(fast_retry_policy: RetryPolicy) -> AgentDispatcher:
    agents = {t: EchoAgent(t) for t in (AgentType.RESEARCH, AgentType.CODING)}
    return AgentDispatcher(agents=agents, retry_policy=fast_retry_policy)


@pytest.fixture
def controller(dispatcher: AgentDispatcher) -> MainController:
    return MainController(planner=RuleBasedPlanner(), dispatcher=dispatcher)
