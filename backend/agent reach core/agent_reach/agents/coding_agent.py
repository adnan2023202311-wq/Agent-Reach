"""
Agents layer: CodingAgent.

Layer: Adapters — implements domain.interfaces.Agent.
See research_agent.py for the note on why lifecycle logging isn't
duplicated here.
"""

from __future__ import annotations

from typing import Any

from domain.interfaces import Agent
from domain.models import AgentType, SubTask


class CodingAgent(Agent):
    @property
    def agent_type(self) -> AgentType:
        return AgentType.CODING

    async def execute(self, subtask: SubTask) -> Any:
        instruction = subtask.input_data.get("instruction", subtask.description)

        # TODO(next milestone): wire this to a real coding backend
        # (e.g. Claude API with tool use for file read/write), then run
        # the project's test suite via infrastructure/tools/tool_manager.py.
        return {
            "instruction": instruction,
            "diff": None,
            "notes": f"(stub) coding agent not yet implemented for: {instruction}",
        }
