"""
Agents layer: ResearchAgent.

Layer: Adapters — implements domain.interfaces.Agent.

Real implementation: answers the query using the injected ModelClient.
This is model-only research — it draws on the model's training data,
not a live web search. Real source-backed research (Blueprint Section
10: search, dedupe, cite) needs a search backend behind ToolManager
plus a Browser Agent, neither of which exists yet — that's a distinct,
later milestone, not a gap in this one.
"""

from __future__ import annotations

from typing import Any

from domain.interfaces import Agent, ModelClient
from domain.models import AgentType, SubTask

SYSTEM_PROMPT = (
    "You are a research assistant. Answer the question clearly and "
    "concisely based on what you know. If the answer depends on very "
    "recent information you can't be sure of, say so explicitly rather "
    "than guessing."
)
"""Public (not underscore-prefixed) so api/routers/agents.py can report
the real prompt instead of a hardcoded copy — api/ is explicitly
allowed to import concrete agents (see docs/ARCHITECTURE.md)."""


class ResearchAgent(Agent):
    def __init__(self, model_client: ModelClient) -> None:
        self._model_client = model_client

    @property
    def agent_type(self) -> AgentType:
        return AgentType.RESEARCH

    async def execute(self, subtask: SubTask) -> Any:
        query = subtask.input_data.get("query", subtask.description)
        answer = await self._model_client.complete(
            messages=[{"role": "user", "content": query}],
            system=SYSTEM_PROMPT,
        )
        return {"query": query, "answer": answer}
