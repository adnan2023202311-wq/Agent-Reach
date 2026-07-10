"""
Distributed layer: Agent Swarm (M10.2 — Agent Swarm Intelligence).

Layer: Application/Core — depends inward on domain/ only.

Supports dynamic creation of collaborative agent swarms. A swarm is a
collection of agents with assigned roles that work in parallel on a
shared objective. The swarm votes on the final answer and reaches
consensus before returning.

Design notes
------------
- A swarm is ephemeral: it's created for one objective, runs to
  completion, and is discarded. State is not persisted.
- Roles are assigned at swarm creation. Each role maps to an AgentType.
- Parallel execution uses asyncio.gather over the shared dispatcher.
- Voting: each agent's output is scored (by default: length + keyword
  match against the objective), and the highest-scoring output wins.
  Custom scorers can be injected.
- Consensus: if the top two scores are within CONSENSUS_THRESHOLD, the
  swarm is said to have reached consensus. Otherwise it's flagged as
  split and the top output is still returned (with a metadata flag).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from domain.models import AgentResult, AgentType, SubTask, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class SwarmRole:
    """One role in a swarm."""

    role_name: str
    agent_type: AgentType
    prompt_suffix: str = ""  # appended to the objective for this role


@dataclass
class SwarmMember:
    """One agent's participation in a swarm."""

    role: SwarmRole
    subtask: SubTask
    result: Optional[AgentResult] = None


@dataclass
class SwarmResult:
    """The outcome of a swarm execution."""

    swarm_id: str
    objective: str
    members: list[SwarmMember] = field(default_factory=list)
    winning_output: Any = None
    winning_role: str = ""
    consensus_reached: bool = False
    scores: dict[str, float] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.FAILED  # default; set to SUCCEEDED on success

    def to_dict(self) -> dict[str, Any]:
        return {
            "swarm_id": self.swarm_id,
            "objective": self.objective,
            "member_count": len(self.members),
            "winning_role": self.winning_role,
            "winning_output": self.winning_output,
            "consensus_reached": self.consensus_reached,
            "scores": dict(self.scores),
            "status": self.status.value,
            "roles": [
                {
                    "role": m.role.role_name,
                    "agent_type": m.role.agent_type.value,
                    "succeeded": m.result.status == TaskStatus.SUCCEEDED if m.result else False,
                }
                for m in self.members
            ],
        }


# Type for a scoring function: (objective, agent_output) -> float
Scorer = Callable[[str, Any], float]


def default_scorer(objective: str, output: Any) -> float:
    """Default scoring: keyword overlap + length bonus.

    Extracts keywords from the objective and counts how many appear in
    the agent's output. Adds a small bonus for longer outputs (more
    substantive). Returns a float score; higher is better.
    """
    if output is None:
        return 0.0
    text = str(output).lower()
    objective_words = set(w.strip(".,!?;:") for w in objective.lower().split() if len(w) > 3)
    if not objective_words:
        return float(len(text)) / 100.0
    matches = sum(1 for w in objective_words if w in text)
    keyword_score = matches / len(objective_words)
    length_bonus = min(len(text) / 1000.0, 1.0) * 0.2
    return keyword_score + length_bonus


class AgentSwarm:
    """A dynamic collection of agents working in parallel on one objective."""

    CONSENSUS_THRESHOLD = 0.15  # if top-2 scores differ by less than this, no consensus

    def __init__(
        self,
        dispatcher: Any,
        scorer: Optional[Scorer] = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._scorer = scorer or default_scorer

    async def execute(
        self,
        objective: str,
        roles: list[SwarmRole],
        *,
        swarm_id: Optional[str] = None,
    ) -> SwarmResult:
        """Create and run a swarm for one objective.

        Each role gets a subtask derived from the objective (+ the
        role's prompt_suffix). All subtasks run in parallel via
        asyncio.gather. The results are scored and a winner is chosen.
        """
        swarm_id = swarm_id or str(uuid.uuid4())
        result = SwarmResult(swarm_id=swarm_id, objective=objective)

        # Build a subtask per role.
        members: list[SwarmMember] = []
        for role in roles:
            desc = f"{objective} {role.prompt_suffix}".strip()
            subtask = SubTask(
                id=f"swarm-{swarm_id}-{role.role_name}",
                description=desc,
                agent_type=role.agent_type,
                input_data={"query": desc, "instruction": desc},
            )
            members.append(SwarmMember(role=role, subtask=subtask))
        result.members = members

        # Execute all subtasks in parallel.
        tasks = [self._dispatcher.dispatch(m.subtask) for m in members]
        agent_results = await asyncio.gather(*tasks, return_exceptions=True)

        for member, ar in zip(members, agent_results):
            if isinstance(ar, Exception):
                # Wrap as a failed AgentResult so scoring still works.
                member.result = AgentResult(
                    subtask_id=member.subtask.id,
                    agent_type=member.role.agent_type,
                    status=TaskStatus.FAILED,
                    attempts=1,
                    error=str(ar),
                    duration_ms=0.0,
                )
            else:
                member.result = ar

        # Score each successful result.
        for member in members:
            if member.result and member.result.status == TaskStatus.SUCCEEDED:
                score = self._scorer(objective, member.result.output)
                result.scores[member.role.role_name] = score

        # Pick the winner.
        if result.scores:
            ranked = sorted(result.scores.items(), key=lambda x: x[1], reverse=True)
            winner_role, winner_score = ranked[0]
            result.winning_role = winner_role
            # Find the winning member's output.
            for m in members:
                if m.role.role_name == winner_role and m.result:
                    result.winning_output = m.result.output
                    break
            # Consensus: top-2 within threshold.
            if len(ranked) >= 2:
                runner_up_score = ranked[1][1]
                result.consensus_reached = (winner_score - runner_up_score) < self.CONSENSUS_THRESHOLD
            else:
                result.consensus_reached = True  # only one → trivially consensus
            result.status = TaskStatus.SUCCEEDED
        else:
            # No successful results — swarm failed.
            result.status = TaskStatus.FAILED
            result.winning_output = "Swarm failed: no agent produced a successful result."

        logger.info(
            "Swarm %s: %d members, winner=%s, consensus=%s, status=%s",
            swarm_id, len(members), result.winning_role, result.consensus_reached, result.status.value,
        )
        return result


class SwarmOrchestrator:
    """Factory + registry for swarms.

    Maintains a catalog of completed swarms for observability. Swarms
    themselves are ephemeral; only their results are kept.
    """

    def __init__(self, dispatcher: Any) -> None:
        self._swarm = AgentSwarm(dispatcher)
        self._history: list[SwarmResult] = []

    async def run(
        self,
        objective: str,
        roles: list[SwarmRole],
    ) -> SwarmResult:
        """Create and execute a swarm, store the result, and return it."""
        result = await self._swarm.execute(objective, roles)
        self._history.append(result)
        # Cap history to prevent unbounded growth.
        if len(self._history) > 100:
            self._history = self._history[-100:]
        return result

    def list_swarms(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent swarm results (newest first)."""
        return [r.to_dict() for r in reversed(self._history[-limit:])]

    def get_swarm(self, swarm_id: str) -> Optional[dict[str, Any]]:
        """Return one swarm result by ID, or None."""
        for r in self._history:
            if r.swarm_id == swarm_id:
                return r.to_dict()
        return None
