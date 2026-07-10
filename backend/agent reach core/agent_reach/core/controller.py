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
        """Assemble agent outputs into a clean conversational response.

        M9 fix (v2.8): previously this did ``f"[{agent_type}] {r.output}"``
        which stringified the entire agent output dict — leaking
        internal payloads like ``{"instruction": "...", "code": "..."}``
        into the chat. Now we extract the user-facing text from each
        agent's output:

        - ResearchAgent returns ``{"query": ..., "answer": ...}`` → use ``answer``
        - CodingAgent returns ``{"instruction": ..., "code": ...}`` → use ``code``
          (or the error/guidance if no code)
        - Any dict with an ``"answer"``, ``"content"``, ``"text"``, or
          ``"output"`` key → use that value
        - A plain string → use as-is
        - Failed agents → include a concise error line

        When there's exactly one successful result, we return its text
        directly (no ``[agent_type]`` prefix) so the user sees a clean
        assistant message. When there are multiple results, we prefix
        each with the agent type for context.
        """
        if not results:
            return "No subtasks were executed."

        # Extract clean text from each result.
        clean_parts: list[tuple[str, str]] = []  # (agent_type_label, text)
        for r in results:
            label = r.agent_type.value
            if r.status != TaskStatus.SUCCEEDED:
                # Failed — include a concise error line.
                error_msg = r.error or "Unknown error"
                # Truncate long errors so the chat doesn't get flooded.
                if len(error_msg) > 300:
                    error_msg = error_msg[:300] + "…"
                clean_parts.append((label, f"(failed: {error_msg})"))
                continue

            output = r.output
            if isinstance(output, str):
                clean_parts.append((label, output))
            elif isinstance(output, dict):
                # Try common text-bearing keys in order of preference.
                for key in ("answer", "code", "content", "text", "output", "result"):
                    val = output.get(key)
                    if val and isinstance(val, str):
                        clean_parts.append((label, val))
                        break
                else:
                    # No recognized text key — skip internal payload.
                    # Don't leak the raw dict into chat.
                    clean_parts.append((label, "(completed)"))
            else:
                # Unknown type — stringify cautiously.
                clean_parts.append((label, str(output)[:500]))

        # If there's exactly one successful result, return it directly
        # (no prefix) for a clean conversational response.
        successful = [p for p in clean_parts if not p[1].startswith("(failed")]
        if len(successful) == 1 and len(clean_parts) == 1:
            return successful[0][1]

        # Multiple results (or mixed success/failure) — prefix each line.
        lines = [f"[{label}] {text}" for label, text in clean_parts]
        return "\n".join(lines)
