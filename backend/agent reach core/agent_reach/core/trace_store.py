"""
Pipeline Trace Store (M9.3 — Runtime Observability).

Persists PipelineTrace objects in memory so every execution becomes
observable and debuggable after the fact — the LangSmith-style
requirement from Milestone 9.3.

Layer: Application/Core — sits next to core/intelligent_pipeline.py,
which produces the traces it stores. This is deliberately NOT a new
package: Milestone 9 extends the existing pipeline, it does not
introduce a parallel observability system (observability/tracing.py's
ObservabilityCollector remains the generic span collector; this store
is specific to PipelineTrace records).

Design notes
------------
- Bounded ring buffer (``max_traces``) so a long-running process never
  grows without limit — same philosophy as ReachLearningEngine's
  ``max_history``.
- Lookup by request_id is O(1) via an index dict that is pruned in
  lockstep with the buffer.
- ``aggregates()`` computes the runtime statistics Milestone 9.4's
  live dashboard needs (error counts, latency percentiles, per-stage
  activity) from real recorded executions — no fabricated numbers.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:  # pragma: no cover - import cycle guard for typing only
    from core.intelligent_pipeline import PipelineTrace


class PipelineTraceStore:
    """Bounded in-memory store for pipeline execution traces."""

    def __init__(self, max_traces: int = 500) -> None:
        if max_traces < 1:
            raise ValueError("max_traces must be >= 1")
        self._max_traces = max_traces
        self._traces: "OrderedDict[str, PipelineTrace]" = OrderedDict()

    # ── Recording ───────────────────────────────────────────────

    def record(self, trace: "PipelineTrace") -> None:
        """Store a completed trace, evicting the oldest when full."""
        self._traces[trace.request_id] = trace
        self._traces.move_to_end(trace.request_id)
        while len(self._traces) > self._max_traces:
            self._traces.popitem(last=False)

    # ── Retrieval ───────────────────────────────────────────────

    def get(self, request_id: str) -> Optional["PipelineTrace"]:
        """Look up a trace by its request id."""
        return self._traces.get(request_id)

    def list_recent(self, limit: int = 50) -> list["PipelineTrace"]:
        """Return the most recent traces, newest first."""
        if limit < 0:
            limit = 0
        items = list(self._traces.values())
        return list(reversed(items))[:limit]

    def __len__(self) -> int:
        return len(self._traces)

    @property
    def max_traces(self) -> int:
        return self._max_traces

    # ── Aggregation (feeds the M9.4 live dashboard) ─────────────

    def aggregates(self) -> dict[str, Any]:
        """Aggregate statistics across every stored trace.

        All values are derived from real executions in the buffer.
        An empty store yields honest zeros.
        """
        traces = list(self._traces.values())
        total = len(traces)
        if total == 0:
            return {
                "total_traces": 0,
                "error_count": 0,
                "error_rate": 0.0,
                "avg_latency_ms": 0.0,
                "p50_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "max_latency_ms": 0.0,
                "stage_activity": {},
                "reflection_retries": 0,
                "memory_items_retrieved": 0,
                "kg_nodes_added": 0,
                "kg_edges_added": 0,
            }

        latencies = sorted(t.total_latency_ms for t in traces)
        error_count = sum(1 for t in traces if t.errors)

        def percentile(values: list[float], pct: float) -> float:
            if not values:
                return 0.0
            idx = min(len(values) - 1, max(0, int(round(pct * (len(values) - 1)))))
            return values[idx]

        stage_activity = {
            "router": sum(1 for t in traces if t.router_active),
            "memory": sum(1 for t in traces if t.memory_active),
            "context": sum(1 for t in traces if t.context_active),
            "moa": sum(1 for t in traces if t.moa_active),
            "reflection": sum(1 for t in traces if t.reflection_active),
            "knowledge_graph": sum(1 for t in traces if t.kg_active),
            "learning": sum(1 for t in traces if t.learning_active),
            "tutti": sum(1 for t in traces if t.tutti_active),
        }

        return {
            "total_traces": total,
            "error_count": error_count,
            "error_rate": error_count / total,
            "avg_latency_ms": sum(latencies) / total,
            "p50_latency_ms": percentile(latencies, 0.50),
            "p95_latency_ms": percentile(latencies, 0.95),
            "max_latency_ms": latencies[-1],
            "stage_activity": stage_activity,
            "reflection_retries": sum(1 for t in traces if t.reflection_retried),
            "memory_items_retrieved": sum(t.memory_items_retrieved for t in traces),
            "kg_nodes_added": sum(t.kg_nodes_added for t in traces),
            "kg_edges_added": sum(t.kg_edges_added for t in traces),
        }

    def clear(self) -> None:
        """Remove all traces. Useful for testing."""
        self._traces.clear()
