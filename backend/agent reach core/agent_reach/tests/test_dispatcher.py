"""
Unit tests for AgentDispatcher's retry/timeout behavior in isolation.

These do not use the `dispatcher` fixture from conftest.py because
each test needs a purpose-built failure pattern (a FlakyAgent) to
prove the retry loop actually retries the right number of times
before giving up.
"""

from __future__ import annotations

import asyncio
from typing import Any

from core.dispatcher import AgentDispatcher
from domain.interfaces import Agent
from domain.models import AgentType, RetryPolicy, SubTask, TaskStatus


class FlakyAgent(Agent):
    """Fails `fail_times` times, then succeeds."""

    def __init__(self, fail_times: int) -> None:
        self._fail_times = fail_times
        self.calls = 0

    @property
    def agent_type(self) -> AgentType:
        return AgentType.RESEARCH

    async def execute(self, subtask: SubTask) -> Any:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise RuntimeError("transient failure")
        return "ok"


class HangingAgent(Agent):
    """Never returns — used to prove the timeout is actually enforced."""

    @property
    def agent_type(self) -> AgentType:
        return AgentType.RESEARCH

    async def execute(self, subtask: SubTask) -> Any:
        await asyncio.sleep(10)
        return "unreachable"


async def test_dispatcher_retries_then_succeeds() -> None:
    agent = FlakyAgent(fail_times=1)
    dispatcher = AgentDispatcher(
        agents={AgentType.RESEARCH: agent},
        retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=0.0, timeout_seconds=1.0),
    )
    subtask = SubTask(agent_type=AgentType.RESEARCH, description="test")

    result = await dispatcher.dispatch(subtask)

    assert result.status == TaskStatus.SUCCEEDED
    assert result.attempts == 2
    assert agent.calls == 2


async def test_dispatcher_gives_up_after_max_attempts() -> None:
    agent = FlakyAgent(fail_times=99)
    dispatcher = AgentDispatcher(
        agents={AgentType.RESEARCH: agent},
        retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=0.0, timeout_seconds=1.0),
    )
    subtask = SubTask(agent_type=AgentType.RESEARCH, description="test")

    result = await dispatcher.dispatch(subtask)

    assert result.status == TaskStatus.FAILED
    assert result.attempts == 2
    assert "after all retries" in (result.error or "")


async def test_dispatcher_enforces_timeout() -> None:
    dispatcher = AgentDispatcher(
        agents={AgentType.RESEARCH: HangingAgent()},
        retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0.0, timeout_seconds=0.05),
    )
    subtask = SubTask(agent_type=AgentType.RESEARCH, description="test")

    result = await dispatcher.dispatch(subtask)

    assert result.status == TaskStatus.FAILED
