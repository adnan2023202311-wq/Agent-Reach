"""
Observability layer: in-process execution tracing.

Inspired by LangSmith tracing and Phoenix diagnostics, but implemented
natively without external cloud dependencies.

Every execution produces a Trace composed of Spans. Spans can be nested
via parent_id to form a tree. All data is kept in memory.

Layer: Infrastructure/Observability — may be imported by any layer.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class SpanStatus(str, Enum):
    """Terminal status of a span."""

    OK = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class Span:
    """A single unit of work inside a Trace."""

    span_id: str
    trace_id: str
    name: str
    start_time: float
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.OK
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    parent_id: Optional[str] = None

    def end(self, status: SpanStatus = SpanStatus.OK) -> None:
        """Mark the span as finished."""
        self.end_time = time.perf_counter()
        self.status = status

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Record an event inside this span."""
        self.events.append(
            {
                "name": name,
                "timestamp": time.perf_counter(),
                "attributes": attributes or {},
            }
        )

    def duration_ms(self) -> Optional[float]:
        """Return duration in milliseconds, or None if not ended."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000


@dataclass
class Trace:
    """A complete execution trace composed of Spans."""

    trace_id: str
    root_span_id: Optional[str] = None
    spans: dict[str, Span] = field(default_factory=dict)
    start_time: float = field(default_factory=time.perf_counter)
    end_time: Optional[float] = None

    def end(self) -> None:
        """Mark the trace as finished."""
        self.end_time = time.perf_counter()

    def duration_ms(self) -> Optional[float]:
        """Return duration in milliseconds, or None if not ended."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000


class ObservabilityCollector:
    """In-memory collector for Traces and Spans.

    Every important execution should produce a trace. The collector
    holds traces in memory for the lifetime of the process.
    """

    def __init__(self) -> None:
        self._traces: dict[str, Trace] = {}

    def start_trace(self, trace_id: Optional[str] = None) -> Trace:
        """Begin a new trace."""
        tid = trace_id or str(uuid.uuid4())
        trace = Trace(trace_id=tid)
        self._traces[tid] = trace
        return trace

    def start_span(
        self,
        trace_id: str,
        name: str,
        parent_id: Optional[str] = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """Begin a new span inside an existing trace."""
        trace = self._traces.get(trace_id)
        if trace is None:
            raise ValueError(f"Trace '{trace_id}' not found")

        span = Span(
            span_id=str(uuid.uuid4()),
            trace_id=trace_id,
            name=name,
            start_time=time.perf_counter(),
            attributes=attributes or {},
            parent_id=parent_id,
        )
        trace.spans[span.span_id] = span

        if parent_id is None and trace.root_span_id is None:
            trace.root_span_id = span.span_id

        return span

    def end_span(
        self,
        trace_id: str,
        span_id: str,
        status: SpanStatus = SpanStatus.OK,
    ) -> None:
        """Finish a span."""
        trace = self._traces.get(trace_id)
        if trace is None:
            return
        span = trace.spans.get(span_id)
        if span is not None:
            span.end(status)

    def end_trace(self, trace_id: str) -> None:
        """Finish a trace."""
        trace = self._traces.get(trace_id)
        if trace is not None:
            trace.end()

    def get_trace(self, trace_id: str) -> Optional[Trace]:
        """Retrieve a trace by ID."""
        return self._traces.get(trace_id)

    def list_traces(self) -> list[Trace]:
        """List all traces."""
        return list(self._traces.values())

    def get_child_spans(self, trace_id: str, parent_id: str) -> list[Span]:
        """Return all direct children of a span."""
        trace = self._traces.get(trace_id)
        if trace is None:
            return []
        return [s for s in trace.spans.values() if s.parent_id == parent_id]

    def clear(self) -> None:
        """Remove all traces. Useful for testing."""
        self._traces.clear()
