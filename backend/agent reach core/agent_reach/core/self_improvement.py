"""
Continuous Self-Improvement Loop (M9.27).

Layer: Application/Core — pure composition of engines that already
exist. It owns no improvement logic of its own:

    Execute          → IntelligentPipeline (every request; M7.5)
    Reflect          → ReflectionEngineV2 (in-pipeline step)
    Learn            → ReachLearningEngine (in-pipeline step)
    Optimize         → SelfOptimizationEngine (M9.14 — safe ops only)
    Update Knowledge → KnowledgeEvolutionEngine (M9.18, in-pipeline)
    Improve Prompt   → PromptEvolutionEngine (M9.20 — proposals only;
                       applying stays a human/API decision)
    Improve Memory   → LongCat consolidate (via the M9.14 safe path)
    Improve Routing  → router.learn_from_history (via the M9.14 path)
    Store Experience → PipelineTraceStore (M9.3) + cycle records here

The loop's own contribution is CADENCE and ACCOUNTING: it decides
when a cycle runs (every ``cycle_every`` pipeline executions, driven
by the M9.24 event stream — no background thread, no nested event
loops) and records exactly what each cycle did.

Honesty contract: a cycle report only contains what actually ran.
Prompt improvement lists generated proposals; it never silently
rewrites prompts.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ImprovementCycle:
    """The record of one completed improvement cycle."""

    cycle_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    trigger_request_id: str = ""
    executions_since_last: int = 0
    optimization_report: dict[str, Any] = field(default_factory=dict)
    prompt_proposals: list[dict[str, Any]] = field(default_factory=list)
    knowledge_stats: dict[str, Any] = field(default_factory=dict)
    learning_stats: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "trigger_request_id": self.trigger_request_id,
            "executions_since_last": self.executions_since_last,
            "optimization_report": dict(self.optimization_report),
            "prompt_proposals": list(self.prompt_proposals),
            "knowledge_stats": dict(self.knowledge_stats),
            "learning_stats": dict(self.learning_stats),
            "errors": list(self.errors),
        }


class SelfImprovementLoop:
    """Run improvement cycles at a fixed execution cadence.

    Parameters
    ----------
    pipeline:
        The shared IntelligentPipeline (reflect/learn/knowledge run
        inside it per-request already).
    optimization_engine:
        The shared M9.14 SelfOptimizationEngine.
    prompt_evolution:
        The shared M9.20 PromptEvolutionEngine.
    cycle_every:
        A cycle runs after this many pipeline executions.
    max_cycles:
        Bound on stored cycle records.
    """

    def __init__(
        self,
        pipeline: Any,
        optimization_engine: Any,
        prompt_evolution: Any,
        cycle_every: int = 10,
        max_cycles: int = 100,
    ) -> None:
        if cycle_every < 1:
            raise ValueError("cycle_every must be >= 1")
        if max_cycles < 1:
            raise ValueError("max_cycles must be >= 1")
        self._pipeline = pipeline
        self._optimization = optimization_engine
        self._prompt_evolution = prompt_evolution
        self._cycle_every = cycle_every
        self._max_cycles = max_cycles
        self._executions_since_cycle = 0
        self._cycles: list[ImprovementCycle] = []
        self._running = False

    @property
    def cycle_every(self) -> int:
        return self._cycle_every

    @property
    def executions_since_cycle(self) -> int:
        return self._executions_since_cycle

    # ── Event integration (M9.24) ───────────────────────────────

    def attach(self, event_hub: Any) -> None:
        """Subscribe to pipeline completions on the runtime event hub.

        The loop advances on real pipeline.completed / pipeline.failed
        events — no polling, no background thread.
        """
        from core.runtime_events import RuntimeEvent

        event_hub.subscribe(RuntimeEvent.PIPELINE_COMPLETED, self._on_pipeline_event)
        event_hub.subscribe(RuntimeEvent.PIPELINE_FAILED, self._on_pipeline_event)

    async def _on_pipeline_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self._executions_since_cycle += 1
        if self._executions_since_cycle >= self._cycle_every:
            await self.run_cycle(trigger_request_id=str(payload.get("request_id", "")))

    # ── Cycle execution ─────────────────────────────────────────

    async def run_cycle(self, trigger_request_id: str = "") -> ImprovementCycle:
        """Run one improvement cycle now.

        Reentrancy-guarded: a cycle triggered while one is already
        running is skipped (recorded as a no-op with an error note)
        rather than stacking.
        """
        cycle = ImprovementCycle(
            trigger_request_id=trigger_request_id,
            executions_since_last=self._executions_since_cycle,
        )
        if self._running:
            cycle.errors.append("cycle skipped: previous cycle still running")
            cycle.finished_at = time.time()
            return cycle

        self._running = True
        self._executions_since_cycle = 0
        try:
            # Optimize (safe ops only — M9.14 contract).
            try:
                cycle.optimization_report = self._optimization.apply()
            except Exception as exc:  # noqa: BLE001 — isolation per stage
                cycle.errors.append(f"optimize: {type(exc).__name__}: {exc}")

            # Improve prompts: generate proposals for every registered
            # prompt. Proposals only — applying is a deliberate act.
            try:
                for name in self._prompt_evolution.library.list_names():
                    for proposal in self._prompt_evolution.propose(name):
                        cycle.prompt_proposals.append(proposal.to_dict())
            except Exception as exc:  # noqa: BLE001
                cycle.errors.append(f"prompts: {type(exc).__name__}: {exc}")

            # Account for knowledge & learning state (updated
            # per-request inside the pipeline; the cycle snapshots
            # real current stats for the record).
            try:
                evolution = self._pipeline._get_knowledge_evolution()
                if evolution is not None:
                    cycle.knowledge_stats = evolution.get_stats()
            except Exception as exc:  # noqa: BLE001
                cycle.errors.append(f"knowledge: {type(exc).__name__}: {exc}")
            try:
                cycle.learning_stats = self._pipeline._get_learning().get_stats()
            except Exception as exc:  # noqa: BLE001
                cycle.errors.append(f"learning: {type(exc).__name__}: {exc}")
        finally:
            self._running = False

        cycle.finished_at = time.time()
        self._cycles.append(cycle)
        if len(self._cycles) > self._max_cycles:
            self._cycles = self._cycles[-self._max_cycles:]
        return cycle

    # ── Introspection ───────────────────────────────────────────

    def get_cycles(self, limit: int = 20) -> list[ImprovementCycle]:
        """Past cycles, newest first."""
        return list(reversed(self._cycles))[: max(0, limit)]

    def get_status(self) -> dict[str, Any]:
        last = self._cycles[-1] if self._cycles else None
        return {
            "cycle_every": self._cycle_every,
            "executions_since_cycle": self._executions_since_cycle,
            "executions_until_next": max(
                0, self._cycle_every - self._executions_since_cycle
            ),
            "total_cycles": len(self._cycles),
            "running": self._running,
            "last_cycle": last.to_dict() if last else None,
        }

    def clear(self) -> None:
        self._cycles.clear()
        self._executions_since_cycle = 0
