"""
Self Optimization Engine (M9.14).

Layer: Application/Core — composes EXISTING subsystems; it owns no
model of its own:

- PipelineTraceStore aggregates (M9.3)  → latency / error analysis
- ReachLearningEngine (M7)              → provider quality learning
- ReachIntelligenceRouter (M7)          → routing preference updates
- LongCatMemoryEngine (M7)              → memory consolidation/pruning
- ContextEngine stats (M7)              → context budget analysis

Contract
--------
analyze() inspects real runtime data and returns OptimizationActions.
Every action is either:

- safe   → apply() may execute it automatically. Safe actions are
           exclusively operations the subsystems already expose as
           safe maintenance (memory.consolidate(), router.
           learn_from_history(), learning.evolve()).
- advisory → returned as a recommendation with the evidence that
           produced it. Never auto-applied.

apply() returns a report with the real before/after measurements of
each executed action. Nothing is fabricated: when there is no data,
analyze() says so instead of inventing findings.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


# Thresholds are conservative and documented — they gate when an
# observation becomes a finding.
_HIGH_P95_LATENCY_MS = 5_000.0
_HIGH_ERROR_RATE = 0.10
_LOW_SUCCESS_RATE = 0.50
_MEMORY_CONSOLIDATION_MIN_SHORT_TERM = 50
_MIN_EXECUTIONS_FOR_PROVIDER_FINDINGS = 5


@dataclass
class OptimizationAction:
    """One finding with an optional safe, executable operation."""

    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    area: str = ""  # latency | errors | cost | memory | routing | providers | context
    finding: str = ""
    recommendation: str = ""
    safe: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "area": self.area,
            "finding": self.finding,
            "recommendation": self.recommendation,
            "safe": self.safe,
            "evidence": dict(self.evidence),
        }


@dataclass
class AppliedAction:
    """Outcome of one executed safe action, with real measurements."""

    action_id: str
    area: str
    operation: str
    before: dict[str, Any]
    after: dict[str, Any]
    succeeded: bool
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "area": self.area,
            "operation": self.operation,
            "before": dict(self.before),
            "after": dict(self.after),
            "succeeded": self.succeeded,
            "error": self.error,
        }


class SelfOptimizationEngine:
    """Analyze real runtime data; apply only safe maintenance."""

    def __init__(self, pipeline: Any) -> None:
        self._pipeline = pipeline
        self._reports: list[dict[str, Any]] = []

    # ── Analysis ────────────────────────────────────────────────

    def analyze(self) -> list[OptimizationAction]:
        """Inspect runtime data and produce findings.

        Honest emptiness: with no traffic there are no findings.
        """
        actions: list[OptimizationAction] = []
        actions.extend(self._analyze_latency_and_errors())
        actions.extend(self._analyze_providers())
        actions.extend(self._analyze_memory())
        actions.extend(self._analyze_routing())
        actions.extend(self._analyze_context())
        return actions

    def _analyze_latency_and_errors(self) -> list[OptimizationAction]:
        actions: list[OptimizationAction] = []
        agg = self._pipeline.trace_store.aggregates()
        if agg["total_traces"] == 0:
            return actions

        if agg["p95_latency_ms"] > _HIGH_P95_LATENCY_MS:
            actions.append(
                OptimizationAction(
                    area="latency",
                    finding=(
                        f"p95 latency is {agg['p95_latency_ms']:.0f}ms across "
                        f"{agg['total_traces']} executions"
                    ),
                    recommendation=(
                        "Investigate the slowest pipeline stages via "
                        "/observatory/traces; consider reducing "
                        "memory_max_context_items or disabling MOA for "
                        "short requests."
                    ),
                    safe=False,
                    evidence={
                        "p95_latency_ms": agg["p95_latency_ms"],
                        "avg_latency_ms": agg["avg_latency_ms"],
                        "total_traces": agg["total_traces"],
                    },
                )
            )
        if agg["error_rate"] > _HIGH_ERROR_RATE:
            actions.append(
                OptimizationAction(
                    area="errors",
                    finding=(
                        f"{agg['error_count']} of {agg['total_traces']} "
                        f"executions recorded stage errors "
                        f"({agg['error_rate']:.0%})"
                    ),
                    recommendation=(
                        "Review error traces via /observatory/traces; "
                        "stage_activity shows which subsystems degrade."
                    ),
                    safe=False,
                    evidence={
                        "error_rate": agg["error_rate"],
                        "error_count": agg["error_count"],
                        "stage_activity": agg["stage_activity"],
                    },
                )
            )
        return actions

    def _analyze_providers(self) -> list[OptimizationAction]:
        actions: list[OptimizationAction] = []
        try:
            learning = self._pipeline._get_learning()
        except Exception:
            return actions
        stats = learning.get_stats()
        if stats["total_executions"] < _MIN_EXECUTIONS_FOR_PROVIDER_FINDINGS:
            return actions

        for provider, pl in learning.compare_providers().items():
            if (
                pl.total_executions >= _MIN_EXECUTIONS_FOR_PROVIDER_FINDINGS
                and pl.success_rate < _LOW_SUCCESS_RATE
            ):
                actions.append(
                    OptimizationAction(
                        area="providers",
                        finding=(
                            f"Provider '{provider}' success rate is "
                            f"{pl.success_rate:.0%} over {pl.total_executions} runs"
                        ),
                        recommendation=(
                            f"Reduce routing weight for '{provider}' or "
                            "verify its configuration."
                        ),
                        safe=False,
                        evidence={
                            "provider": provider,
                            "success_rate": pl.success_rate,
                            "executions": pl.total_executions,
                        },
                    )
                )
        # Learning evolution is a safe periodic maintenance operation.
        actions.append(
            OptimizationAction(
                area="providers",
                finding=(
                    f"Learning engine holds {stats['total_executions']} execution "
                    f"records at generation {stats['generation']}"
                ),
                recommendation="Evolve the learning engine (consolidates recommendations).",
                safe=True,
                evidence={"operation": "learning.evolve", **stats},
            )
        )
        return actions

    def _analyze_memory(self) -> list[OptimizationAction]:
        actions: list[OptimizationAction] = []
        try:
            memory = self._pipeline._get_memory()
        except Exception:
            return actions
        counts = memory.get_stats()["memory_counts"]
        if counts["short_term"] >= _MEMORY_CONSOLIDATION_MIN_SHORT_TERM:
            actions.append(
                OptimizationAction(
                    area="memory",
                    finding=(
                        f"{counts['short_term']} short-term memories accumulated "
                        f"({counts['total']} total)"
                    ),
                    recommendation="Consolidate high-value short-term memories to long-term.",
                    safe=True,
                    evidence={"operation": "memory.consolidate", **counts},
                )
            )
        return actions

    def _analyze_routing(self) -> list[OptimizationAction]:
        actions: list[OptimizationAction] = []
        try:
            router = self._pipeline._get_router()
        except Exception:
            return actions
        health = router.get_provider_health()
        called = {p: h for p, h in health.items() if h["total_calls"] > 0}
        if called:
            actions.append(
                OptimizationAction(
                    area="routing",
                    finding=(
                        f"Router has live statistics for {len(called)} providers"
                    ),
                    recommendation=(
                        "Re-learn provider preferences from recorded history."
                    ),
                    safe=True,
                    evidence={"operation": "router.learn_from_history", "providers": list(called)},
                )
            )
        return actions

    def _analyze_context(self) -> list[OptimizationAction]:
        actions: list[OptimizationAction] = []
        agg = self._pipeline.trace_store.aggregates()
        if agg["total_traces"] == 0:
            return actions
        traces = self._pipeline.list_traces(
            limit=self._pipeline.trace_store.max_traces
        )
        with_budget = [t for t in traces if t.context_budget > 0]
        if not with_budget:
            return actions
        utilization = sum(
            t.context_tokens_used / t.context_budget for t in with_budget
        ) / len(with_budget)
        if utilization > 0.9:
            actions.append(
                OptimizationAction(
                    area="context",
                    finding=(
                        f"Average context utilization is {utilization:.0%} of budget "
                        f"across {len(with_budget)} executions"
                    ),
                    recommendation=(
                        "Contexts are near their budget — enable memory "
                        "compression or raise the context budget."
                    ),
                    safe=False,
                    evidence={
                        "avg_utilization": utilization,
                        "executions": len(with_budget),
                    },
                )
            )
        return actions

    # ── Application ─────────────────────────────────────────────

    def apply(
        self, actions: Optional[list[OptimizationAction]] = None
    ) -> dict[str, Any]:
        """Execute the safe actions; report real before/after data.

        Advisory actions are returned untouched in `skipped`.
        """
        actions = actions if actions is not None else self.analyze()
        applied: list[AppliedAction] = []
        skipped: list[OptimizationAction] = []

        for action in actions:
            if not action.safe:
                skipped.append(action)
                continue
            applied.append(self._apply_one(action))

        report = {
            "report_id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "applied": [a.to_dict() for a in applied],
            "skipped": [a.to_dict() for a in skipped],
            "applied_count": len(applied),
            "skipped_count": len(skipped),
        }
        self._reports.append(report)
        return report

    def _apply_one(self, action: OptimizationAction) -> AppliedAction:
        operation = str(action.evidence.get("operation", ""))
        try:
            if operation == "memory.consolidate":
                memory = self._pipeline._get_memory()
                before = dict(memory.get_stats()["memory_counts"])
                promoted = memory.consolidate()
                after = dict(memory.get_stats()["memory_counts"])
                after["promoted"] = promoted
                return AppliedAction(
                    action_id=action.action_id,
                    area=action.area,
                    operation=operation,
                    before=before,
                    after=after,
                    succeeded=True,
                )
            if operation == "router.learn_from_history":
                router = self._pipeline._get_router()
                before = {"preferred_provider": router.preferred_provider}
                router.learn_from_history()
                after = {"preferred_provider": router.preferred_provider}
                return AppliedAction(
                    action_id=action.action_id,
                    area=action.area,
                    operation=operation,
                    before=before,
                    after=after,
                    succeeded=True,
                )
            if operation == "learning.evolve":
                learning = self._pipeline._get_learning()
                before = {"generation": learning.get_stats()["generation"]}
                learning.evolve()
                after = {"generation": learning.get_stats()["generation"]}
                return AppliedAction(
                    action_id=action.action_id,
                    area=action.area,
                    operation=operation,
                    before=before,
                    after=after,
                    succeeded=True,
                )
            return AppliedAction(
                action_id=action.action_id,
                area=action.area,
                operation=operation or "unknown",
                before={},
                after={},
                succeeded=False,
                error=f"No executor for operation '{operation}'",
            )
        except Exception as exc:  # noqa: BLE001 — isolation boundary
            return AppliedAction(
                action_id=action.action_id,
                area=action.area,
                operation=operation,
                before={},
                after={},
                succeeded=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    # ── Reports ─────────────────────────────────────────────────

    def get_reports(self, limit: int = 20) -> list[dict[str, Any]]:
        """Past optimization reports, newest first."""
        return list(reversed(self._reports))[: max(0, limit)]

    def clear(self) -> None:
        self._reports.clear()
