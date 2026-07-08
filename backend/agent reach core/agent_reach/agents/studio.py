"""
Agent Studio runtime (M9.9).

Layer: Application — composes the existing IntelligentPipeline; it
does not create a parallel execution path.

Implements the M9.9 workflow:

    Create Agent → Configure → Save → Run → Observe → Debug → Improve

- Definitions are versioned: every save records the prior revision,
  so "Improve" is auditable (get_versions).
- Run executes through the SHARED IntelligentPipeline: the agent's
  system prompt and configuration wrap the user prompt, and the
  pipeline's full stack (router, memory, KG, reflection, learning)
  participates. The returned record carries the REAL request_id of
  the persisted pipeline trace (M9.3), which is what makes "Observe"
  and "Debug" live: the studio links straight into the observatory.
- Execution history per agent is a bounded buffer of real runs with
  real latency and outcome — nothing fabricated.
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class StudioAgentDefinition:
    """One configurable studio agent."""

    agent_id: str = ""
    name: str = ""
    description: str = ""
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)
    model_provider: str = "anthropic"
    model_id: str = ""
    temperature: float = 0.3
    max_tokens: int = 2048
    memory_enabled: bool = True
    reasoning: str = "balanced"
    version: int = 1
    published: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "tools": list(self.tools),
            "model_provider": self.model_provider,
            "model_id": self.model_id,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "memory_enabled": self.memory_enabled,
            "reasoning": self.reasoning,
            "version": self.version,
            "published": self.published,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class StudioRunRecord:
    """One real execution of a studio agent."""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    agent_version: int = 1
    prompt: str = ""
    answer: str = ""
    status: str = ""
    request_id: str = ""
    latency_ms: float = 0.0
    started_at: float = field(default_factory=time.time)
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "prompt": self.prompt,
            "answer": self.answer,
            "status": self.status,
            "request_id": self.request_id,
            "latency_ms": self.latency_ms,
            "started_at": self.started_at,
            "error": self.error,
        }


class AgentStudio:
    """Create, configure, save, run, observe, and improve custom agents.

    Parameters
    ----------
    pipeline:
        The shared IntelligentPipeline. Injected — the studio never
        builds its own execution stack.
    max_history_per_agent:
        Bound on stored run records per agent.
    """

    def __init__(self, pipeline: Any, max_history_per_agent: int = 200) -> None:
        if max_history_per_agent < 1:
            raise ValueError("max_history_per_agent must be >= 1")
        self._pipeline = pipeline
        self._agents: dict[str, StudioAgentDefinition] = {}
        self._versions: dict[str, list[dict[str, Any]]] = {}
        self._history: dict[str, deque[StudioRunRecord]] = {}
        self._max_history = max_history_per_agent

    # ── Create / Configure / Save ───────────────────────────────

    def save(
        self,
        name: str,
        *,
        agent_id: str = "",
        description: str = "",
        system_prompt: str = "",
        tools: Optional[list[str]] = None,
        model_provider: str = "anthropic",
        model_id: str = "",
        temperature: float = 0.3,
        max_tokens: int = 2048,
        memory_enabled: bool = True,
        reasoning: str = "balanced",
    ) -> StudioAgentDefinition:
        """Create or update an agent definition.

        Updating an existing agent_id records the prior revision and
        bumps ``version``. Validation is strict — empty names and
        out-of-range parameters are rejected, not silently fixed.
        """
        if not name.strip():
            raise ValueError("Agent name must not be empty")
        if not 0.0 <= temperature <= 2.0:
            raise ValueError("temperature must be within [0.0, 2.0]")
        if max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")

        resolved_id = agent_id or name.lower().strip().replace(" ", "_")
        existing = self._agents.get(resolved_id)

        if existing is not None:
            self._versions.setdefault(resolved_id, []).append(existing.to_dict())
            definition = StudioAgentDefinition(
                agent_id=resolved_id,
                name=name,
                description=description,
                system_prompt=system_prompt,
                tools=list(tools or []),
                model_provider=model_provider,
                model_id=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
                memory_enabled=memory_enabled,
                reasoning=reasoning,
                version=existing.version + 1,
                published=existing.published,
                created_at=existing.created_at,
            )
        else:
            definition = StudioAgentDefinition(
                agent_id=resolved_id,
                name=name,
                description=description,
                system_prompt=system_prompt,
                tools=list(tools or []),
                model_provider=model_provider,
                model_id=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
                memory_enabled=memory_enabled,
                reasoning=reasoning,
            )

        self._agents[resolved_id] = definition
        return definition

    def get(self, agent_id: str) -> Optional[StudioAgentDefinition]:
        return self._agents.get(agent_id)

    def list_agents(self, published_only: bool = False) -> list[StudioAgentDefinition]:
        agents = sorted(self._agents.values(), key=lambda a: a.created_at)
        if published_only:
            agents = [a for a in agents if a.published]
        return agents

    def delete(self, agent_id: str) -> bool:
        if agent_id not in self._agents:
            return False
        del self._agents[agent_id]
        self._versions.pop(agent_id, None)
        self._history.pop(agent_id, None)
        return True

    def get_versions(self, agent_id: str) -> list[dict[str, Any]]:
        """Prior revisions, oldest first ('Improve' audit trail)."""
        return [dict(v) for v in self._versions.get(agent_id, [])]

    def publish(self, agent_id: str) -> StudioAgentDefinition:
        """Mark an agent as published. Unknown ids raise KeyError."""
        definition = self._require(agent_id)
        definition.published = True
        definition.updated_at = time.time()
        return definition

    def unpublish(self, agent_id: str) -> StudioAgentDefinition:
        definition = self._require(agent_id)
        definition.published = False
        definition.updated_at = time.time()
        return definition

    # ── Run / Observe / Debug ───────────────────────────────────

    async def run(self, agent_id: str, prompt: str) -> StudioRunRecord:
        """Execute a studio agent through the real pipeline.

        The agent's system prompt and configuration frame the user
        prompt; the pipeline handles routing, memory, knowledge,
        reflection, and learning as for any other request. The
        record's request_id links to the persisted pipeline trace.
        """
        definition = self._require(agent_id)
        if not prompt.strip():
            raise ValueError("prompt must not be empty")

        record = StudioRunRecord(
            agent_id=agent_id,
            agent_version=definition.version,
            prompt=prompt,
        )
        framed = self._frame_prompt(definition, prompt)
        start = time.perf_counter()
        try:
            result = await self._pipeline.process(
                framed,
                session_id=f"studio:{agent_id}",
                extra_context={
                    "studio_agent": agent_id,
                    "studio_agent_version": definition.version,
                },
            )
            record.answer = result.outcome.answer
            record.status = result.outcome.status.value
            record.request_id = result.trace.request_id
        except Exception as exc:  # noqa: BLE001 — isolation boundary
            record.status = "failed"
            record.error = f"{type(exc).__name__}: {exc}"
        record.latency_ms = (time.perf_counter() - start) * 1000

        history = self._history.setdefault(
            agent_id, deque(maxlen=self._max_history)
        )
        history.append(record)
        return record

    def get_history(self, agent_id: str, limit: int = 50) -> list[StudioRunRecord]:
        """Real run records for an agent, newest first."""
        records = list(self._history.get(agent_id, []))
        return list(reversed(records))[: max(0, limit)]

    def get_metrics(self, agent_id: str) -> dict[str, Any]:
        """Aggregate execution metrics for one agent."""
        records = list(self._history.get(agent_id, []))
        total = len(records)
        if total == 0:
            return {
                "total_runs": 0,
                "successes": 0,
                "failures": 0,
                "success_rate": 0.0,
                "avg_latency_ms": 0.0,
            }
        successes = sum(1 for r in records if r.status == "succeeded")
        return {
            "total_runs": total,
            "successes": successes,
            "failures": total - successes,
            "success_rate": successes / total,
            "avg_latency_ms": sum(r.latency_ms for r in records) / total,
        }

    def clear(self) -> None:
        """Remove all definitions, versions, and history. For testing."""
        self._agents.clear()
        self._versions.clear()
        self._history.clear()

    # ── Internals ───────────────────────────────────────────────

    def _require(self, agent_id: str) -> StudioAgentDefinition:
        definition = self._agents.get(agent_id)
        if definition is None:
            raise KeyError(f"Studio agent '{agent_id}' not found")
        return definition

    @staticmethod
    def _frame_prompt(definition: StudioAgentDefinition, prompt: str) -> str:
        """Compose the agent's configuration around the user prompt."""
        parts: list[str] = []
        if definition.system_prompt:
            parts.append(f"[System: {definition.system_prompt}]")
        if definition.tools:
            parts.append(f"[Available tools: {', '.join(definition.tools)}]")
        parts.append(prompt)
        return "\n".join(parts)
