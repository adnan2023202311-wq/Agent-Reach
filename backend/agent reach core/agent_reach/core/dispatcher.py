"""
Core layer: AgentDispatcher.

Layer: Application/Core — depends inward on domain/ only. Never
imports a concrete Agent class (ResearchAgent, CodingAgent, ...) —
see composition.py for where agents are actually registered.

Owns: routing a SubTask to its Agent, retrying on failure with
backoff, enforcing a timeout, and turning every outcome (success,
failure, timeout) into an AgentResult — callers never need a
try/except around dispatch() for expected task failures.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Mapping, Optional

from domain.exceptions import AgentExecutionError, AgentNotRegisteredError
from domain.interfaces import Agent
from domain.models import AgentResult, AgentType, RetryPolicy, SubTask, TaskStatus

logger = logging.getLogger(__name__)


class AgentDispatcher:
    """Routes subtasks to registered agents and enforces retry/timeout policy.

    Agents are injected as a ready-made mapping rather than constructed
    here (Dependency Inversion Principle) — composition.py builds the
    mapping in production; tests/conftest.py builds a fake one for
    tests. Neither this class nor MainController needs to change for
    either case.
    """

    def __init__(
        self,
        agents: Mapping[AgentType, Agent],
        retry_policy: Optional[RetryPolicy] = None,
    ) -> None:
        self._agents = dict(agents)
        self._retry_policy = retry_policy or RetryPolicy()

    def registered_agent_types(self) -> list[AgentType]:
        """Which AgentTypes actually have an Agent registered.

        Added for api/routers/agents.py — reflects real wiring instead
        of the Blueprint's full planned list of nine agent types. If an
        agent isn't in composition.py's registry, it won't appear here,
        which is the honest answer.
        """
        return list(self._agents.keys())

    async def dispatch(self, subtask: SubTask) -> AgentResult:
        """Execute one subtask and return its outcome.

        Raises:
            AgentNotRegisteredError: if no agent is registered for
                `subtask.agent_type`. This is a configuration bug, not
                a task failure, so it is raised immediately rather than
                wrapped in a failed AgentResult.
        """
        agent = self._agents.get(subtask.agent_type)
        if agent is None:
            raise AgentNotRegisteredError(subtask.agent_type.value)

        start = time.perf_counter()
        last_error: Optional[BaseException] = None
        max_attempts = self._retry_policy.max_attempts

        for attempt in range(1, max_attempts + 1):
            try:
                output = await asyncio.wait_for(
                    agent.execute(subtask),
                    timeout=self._retry_policy.timeout_seconds,
                )
                duration_ms = self._elapsed_ms(start)
                logger.info(
                    "subtask=%s agent=%s succeeded in %.1fms (attempt %s/%s)",
                    subtask.id, subtask.agent_type.value, duration_ms, attempt, max_attempts,
                )
                return AgentResult(
                    subtask_id=subtask.id,
                    agent_type=subtask.agent_type,
                    status=TaskStatus.SUCCEEDED,
                    attempts=attempt,
                    output=output,
                    duration_ms=duration_ms,
                )
            except Exception as exc:  # noqa: BLE001 - centralized error handling by design
                last_error = exc
                logger.warning(
                    "subtask=%s agent=%s attempt=%s/%s failed: %s",
                    subtask.id, subtask.agent_type.value, attempt, max_attempts, exc,
                )
                if attempt < max_attempts:
                    await asyncio.sleep(self._retry_policy.backoff_seconds * attempt)

        wrapped = AgentExecutionError(subtask.agent_type.value, subtask.id, last_error)
        return AgentResult(
            subtask_id=subtask.id,
            agent_type=subtask.agent_type,
            status=TaskStatus.FAILED,
            attempts=max_attempts,
            error=str(wrapped),
            duration_ms=self._elapsed_ms(start),
        )

    @staticmethod
    def _elapsed_ms(start: float) -> float:
        return (time.perf_counter() - start) * 1000
