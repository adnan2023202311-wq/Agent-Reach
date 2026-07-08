"""
Multi-Agent Collaboration Engine (M9.29).

Layer: Application/Core — composes EXISTING machinery:

    Task decomposition → the injected Planner (RuleBasedPlanner today;
                         any Planner implementation works)
    Dynamic delegation → AgentDispatcher (retry/timeout policy intact)
    Parallel execution → asyncio.gather over dispatcher.dispatch with
                         dependency-wave scheduling: subtasks whose
                         depends_on are satisfied run concurrently.
                         This finally HONORS SubTask.depends_on (the
                         long-documented "defined but not honored"
                         gap) without changing MainController's
                         sequential contract.
    Shared reasoning   → AgentMessenger (M3): every wave broadcast
                         shares upstream outputs with later agents
                         through the real message bus; the message
                         history is the audit trail.
    Consensus          → the same first-N-chars agreement rule MOA's
                         consensus mode uses, applied across agent
                         outputs of the final wave.
    Conflict resolution→ when outputs disagree, resolution is
                         explicit and recorded: highest-success-wave
                         output wins, with the losing outputs kept in
                         the record (never silently discarded).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

from core.agent_communication import AgentMessage, AgentMessenger
from core.dispatcher import AgentDispatcher
from domain.interfaces import Planner
from domain.models import AgentResult, SubTask, TaskPlan, TaskStatus


@dataclass
class CollaborationRecord:
    """Full record of one collaborative execution."""

    collaboration_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    request: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    plan_id: str = ""
    waves: list[list[str]] = field(default_factory=list)  # subtask ids per wave
    results: list[AgentResult] = field(default_factory=list)
    consensus: bool = False
    consensus_answer: str = ""
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    shared_messages: int = 0
    status: str = "running"

    def to_dict(self) -> dict[str, Any]:
        return {
            "collaboration_id": self.collaboration_id,
            "request": self.request,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "plan_id": self.plan_id,
            "waves": [list(w) for w in self.waves],
            "results": [
                {
                    "subtask_id": r.subtask_id,
                    "agent_type": r.agent_type.value,
                    "status": r.status.value,
                    "output": str(r.output)[:500] if r.output else None,
                    "error": r.error,
                }
                for r in self.results
            ],
            "consensus": self.consensus,
            "consensus_answer": self.consensus_answer,
            "conflicts": list(self.conflicts),
            "shared_messages": self.shared_messages,
            "status": self.status,
        }


class CollaborationEngine:
    """Coordinate multiple agents on one request, in dependency waves."""

    def __init__(
        self,
        planner: Planner,
        dispatcher: AgentDispatcher,
        messenger: Optional[AgentMessenger] = None,
        max_records: int = 200,
    ) -> None:
        if max_records < 1:
            raise ValueError("max_records must be >= 1")
        self._planner = planner
        self._dispatcher = dispatcher
        self._messenger = messenger or AgentMessenger()
        self._records: dict[str, CollaborationRecord] = {}
        self._max_records = max_records

    @property
    def messenger(self) -> AgentMessenger:
        return self._messenger

    # ── Execution ───────────────────────────────────────────────

    async def collaborate(self, request: str) -> CollaborationRecord:
        """Decompose, delegate, and execute in parallel waves."""
        if not request.strip():
            raise ValueError("request must not be empty")

        record = CollaborationRecord(request=request)
        plan = await self._planner.create_plan(request)
        record.plan_id = plan.id

        waves = self._build_waves(plan)
        record.waves = [[s.id for s in wave] for wave in waves]

        completed: dict[str, AgentResult] = {}
        for wave in waves:
            # Share upstream outputs before the wave runs (real
            # messages through the M3 bus — the audit trail).
            for subtask in wave:
                upstream = [
                    completed[dep] for dep in subtask.depends_on
                    if dep in completed
                ]
                for dep_result in upstream:
                    self._messenger.send(
                        AgentMessage(
                            sender=f"agent:{dep_result.agent_type.value}",
                            recipient=f"agent:{subtask.agent_type.value}",
                            message_type="shared_context",
                            payload={
                                "collaboration_id": record.collaboration_id,
                                "subtask_id": subtask.id,
                                "upstream_subtask_id": dep_result.subtask_id,
                                "output": str(dep_result.output)[:1000]
                                if dep_result.output
                                else "",
                            },
                        )
                    )
                    record.shared_messages += 1

            # Parallel execution of the whole wave.
            wave_results = await asyncio.gather(
                *(self._dispatcher.dispatch(subtask) for subtask in wave)
            )
            for result in wave_results:
                completed[result.subtask_id] = result
                record.results.append(result)

        self._resolve(record)
        record.finished_at = time.time()
        record.status = (
            "succeeded"
            if any(r.status == TaskStatus.SUCCEEDED for r in record.results)
            else "failed"
        )
        self._records[record.collaboration_id] = record
        self._evict()
        return record

    # ── Wave building (honors depends_on) ───────────────────────

    @staticmethod
    def _build_waves(plan: TaskPlan) -> list[list[SubTask]]:
        """Topological waves: each wave's dependencies are all in
        earlier waves. Unknown/cyclic dependencies fail loudly."""
        pending = {s.id: s for s in plan.subtasks}
        known_ids = set(pending)
        for subtask in plan.subtasks:
            unknown = [d for d in subtask.depends_on if d not in known_ids]
            if unknown:
                raise ValueError(
                    f"Subtask '{subtask.id}' depends on unknown subtasks: {unknown}"
                )

        waves: list[list[SubTask]] = []
        resolved: set[str] = set()
        while pending:
            wave = [
                s for s in pending.values()
                if all(d in resolved for d in s.depends_on)
            ]
            if not wave:
                raise ValueError(
                    f"Dependency cycle among subtasks: {sorted(pending)}"
                )
            for subtask in wave:
                del pending[subtask.id]
                resolved.add(subtask.id)
            waves.append(wave)
        return waves

    # ── Consensus & conflict resolution ─────────────────────────

    @staticmethod
    def _normalize(output: Any) -> str:
        return str(output)[:200].strip().lower()

    def _resolve(self, record: CollaborationRecord) -> None:
        """Consensus check + explicit conflict resolution.

        Uses the same agreement rule as MOA consensus (normalized
        prefix match). On conflict, the majority output wins; ties
        fall to the successful result that finished in the latest
        wave (it saw the most shared context). Losing outputs are
        preserved in the record.
        """
        successful = [
            r for r in record.results
            if r.status == TaskStatus.SUCCEEDED and r.output
        ]
        if not successful:
            return
        normalized = [self._normalize(r.output) for r in successful]
        tally = Counter(normalized)
        top_text, top_count = tally.most_common(1)[0]

        if len(tally) == 1:
            record.consensus = True
            record.consensus_answer = str(successful[0].output)
            return

        # Conflict: record it and resolve explicitly.
        record.consensus = False
        majority = [
            r for r in successful if self._normalize(r.output) == top_text
        ]
        if top_count > len(successful) - top_count:
            winner = majority[-1]
            rule = "majority"
        else:
            winner = successful[-1]  # latest wave — most shared context
            rule = "latest_wave"
        record.consensus_answer = str(winner.output)
        record.conflicts.append(
            {
                "rule": rule,
                "winner_subtask_id": winner.subtask_id,
                "options": [
                    {
                        "subtask_id": r.subtask_id,
                        "agent_type": r.agent_type.value,
                        "output": str(r.output)[:300],
                    }
                    for r in successful
                ],
            }
        )

    # ── Introspection ───────────────────────────────────────────

    def get_record(self, collaboration_id: str) -> Optional[CollaborationRecord]:
        return self._records.get(collaboration_id)

    def list_records(self, limit: int = 20) -> list[CollaborationRecord]:
        records = sorted(
            self._records.values(), key=lambda r: r.started_at, reverse=True
        )
        return records[: max(0, limit)]

    def get_shared_reasoning(self, collaboration_id: str) -> list[dict[str, Any]]:
        """The real shared-context messages of one collaboration."""
        return [
            {
                "id": m.id,
                "sender": m.sender,
                "recipient": m.recipient,
                "timestamp": m.timestamp,
                "payload": dict(m.payload),
            }
            for m in self._messenger.get_history(message_type="shared_context")
            if m.payload.get("collaboration_id") == collaboration_id
        ]

    def clear(self) -> None:
        self._records.clear()
        self._messenger.clear_history()

    def _evict(self) -> None:
        while len(self._records) > self._max_records:
            oldest = min(self._records.values(), key=lambda r: r.started_at)
            del self._records[oldest.collaboration_id]
