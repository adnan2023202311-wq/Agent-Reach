"""
Core layer: MainController.

Layer: Application/Core — the single orchestration use case, and the
only class the interface layer (api/) calls directly.

Depends only on domain.interfaces.Planner and AgentDispatcher (which
itself depends only on domain/). It knows nothing about FastAPI,
Settings, or which concrete agents exist — that wiring happens once,
in composition.py.
"""

from __future__ import annotations

import logging

from core.dispatcher import AgentDispatcher
from domain.interfaces import Planner
from domain.models import AgentResult, AgentType, TaskExecutionOutcome, TaskStatus

logger = logging.getLogger(__name__)


class MainController:
    """Coordinates planning and dispatch for a single user request.

    Both collaborators are required constructor arguments (no
    `planner or DefaultPlanner()` fallback) — a class should never be
    responsible for constructing its own dependencies. Use
    composition.build_default_controller() to get a fully
    wired instance with sensible defaults.
    """

    def __init__(self, planner: Planner, dispatcher: AgentDispatcher) -> None:
        self._planner = planner
        self._dispatcher = dispatcher

    def registered_agent_types(self) -> list[AgentType]:
        """Passthrough to AgentDispatcher.

        api/ only ever depends on MainController (see api/dependencies.py)
        — this exists so api/routers/agents.py doesn't need to reach
        past the controller into `controller._dispatcher` directly,
        which would break that rule for a one-line convenience.
        """
        return self._dispatcher.registered_agent_types()

    async def handle_request(self, message: str) -> TaskExecutionOutcome:
        logger.info("planning request: %s", message)
        plan = await self._planner.create_plan(message)

        # Sequential for now — plan.subtasks[].depends_on is defined
        # but not yet honored. See docs/ARCHITECTURE.md, "Remaining
        # weaknesses", before parallelizing this with asyncio.gather.
        results: list[AgentResult] = []
        for subtask in plan.subtasks:
            results.append(await self._dispatcher.dispatch(subtask))

        overall_status = (
            TaskStatus.SUCCEEDED
            if all(r.status == TaskStatus.SUCCEEDED for r in results)
            else TaskStatus.FAILED
        )
        return TaskExecutionOutcome(
            plan=plan,
            results=results,
            answer=self._assemble_answer(results),
            status=overall_status,
        )

    @staticmethod
    def _assemble_answer(results: list[AgentResult]) -> str:
        """Naive concatenation of subtask outputs into one answer string.

        TODO(next milestone): replace with a real synthesis step (e.g.
        feed all subtask outputs back into a model call that writes a
        coherent final answer). Intentionally left simple here — this
        milestone's scope is orchestration correctness, not answer
        quality (Blueprint Section 8 assigns "final response assembly"
        to the Main Controller, which is why this logic lives here and
        not in api/).
        """
        if not results:
            return "No subtasks were executed."
        lines = [
            f"[{r.agent_type.value}] {r.output}"
            if r.status == TaskStatus.SUCCEEDED
            else f"[{r.agent_type.value}] FAILED: {r.error}"
            for r in results
        ]
        return "\n".join(lines)
