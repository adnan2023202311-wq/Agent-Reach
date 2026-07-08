"""
Agents layer: CodingAgent.

Layer: Adapters — implements domain.interfaces.Agent.

M9 completion: accepts an optional ModelClient for real code generation.
When no client is provided, operates in advisory mode — it inspects the
instruction and returns structured guidance without generating code.
"""

from __future__ import annotations

from typing import Any, Optional

from domain.interfaces import Agent, ModelClient
from domain.models import AgentType, SubTask

CODING_SYSTEM_PROMPT = (
    "You are a coding assistant. Generate clean, well-documented code based "
    "on the instructions. Include imports, error handling, and brief comments. "
    "Return ONLY the code, no markdown fences or explanatory text unless "
    "explicitly asked."
)


class CodingAgent(Agent):
    def __init__(self, model_client: Optional[ModelClient] = None) -> None:
        self._model_client = model_client

    @property
    def agent_type(self) -> AgentType:
        return AgentType.CODING

    async def execute(self, subtask: SubTask) -> Any:
        instruction = subtask.input_data.get("instruction", subtask.description)

        if self._model_client is not None:
            try:
                code = await self._model_client.complete(
                    messages=[{"role": "user", "content": instruction}],
                    system=CODING_SYSTEM_PROMPT,
                )
                return {
                    "instruction": instruction,
                    "code": code,
                    "source": "model",
                }
            except Exception as exc:
                return {
                    "instruction": instruction,
                    "code": None,
                    "error": str(exc),
                    "source": "model_error",
                }

        # Advisory mode — no model client available.
        return {
            "instruction": instruction,
            "code": None,
            "source": "advisory",
            "guidance": _derive_guidance(instruction),
        }


def _derive_guidance(instruction: str) -> str:
    lowered = instruction.lower()
    if any(kw in lowered for kw in ("api", "endpoint", "fastapi", "router")):
        return "Create a FastAPI router with Pydantic models, dependency injection, and proper error handling."
    if any(kw in lowered for kw in ("test", "pytest", "unit test")):
        return "Write a pytest test with fixtures, parametrize, and assert for edge cases."
    if any(kw in lowered for kw in ("database", "sql", "orm", "model")):
        return "Define SQLAlchemy/domain models with proper relationships, indexes, and migrations."
    if any(kw in lowered for kw in ("fix", "bug", "error", "issue")):
        return "Isolate the bug with a minimal reproduction, add a regression test, then apply the fix."
    return "Apply Clean Architecture principles, write SOLID code with dependency injection, and include docstrings."
