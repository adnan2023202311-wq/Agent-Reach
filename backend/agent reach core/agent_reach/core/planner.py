"""
Core layer: default Planner implementation.

Layer: Application/Core — depends inward on domain/ only.

RuleBasedPlanner is intentionally simple (keyword matching, always
produces exactly one subtask) so the Controller -> Planner -> Dispatcher
pipeline can be exercised end-to-end with zero external dependencies
and zero API keys. Add an LLMPlanner alongside it later by implementing
domain.interfaces.Planner — no other code needs to change to use it
(Open/Closed Principle).
"""

from __future__ import annotations

from domain.interfaces import Planner
from domain.models import AgentType, SubTask, TaskPlan

# Keyword -> AgentType routing table. First match wins; order matters.
_KEYWORD_ROUTES: dict[AgentType, tuple[str, ...]] = {
    AgentType.CODING: ("code", "bug", "repo", "function", "كود", "برمج"),
    AgentType.RESEARCH: ("research", "find out", "compare", "ابحث"),
    AgentType.WRITING: ("write", "article", "draft", "اكتب"),
    AgentType.IMAGE: ("image", "illustration", "picture", "صورة"),
    AgentType.NEWS: ("news", "headline", "أخبار"),
    AgentType.BROWSER: ("browse", "scrape", "login", "download"),
}
_DEFAULT_AGENT_TYPE = AgentType.RESEARCH


class RuleBasedPlanner(Planner):
    """Single-subtask planner that guesses an AgentType from keywords."""

    async def create_plan(self, request: str) -> TaskPlan:
        agent_type = self._guess_agent_type(request)
        subtask = SubTask(agent_type=agent_type, description=request)
        return TaskPlan(original_request=request, subtasks=[subtask])

    @staticmethod
    def _guess_agent_type(request: str) -> AgentType:
        lowered = request.lower()
        for agent_type, keywords in _KEYWORD_ROUTES.items():
            if any(keyword in lowered for keyword in keywords):
                return agent_type
        return _DEFAULT_AGENT_TYPE
