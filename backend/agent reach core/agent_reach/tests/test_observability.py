"""Tests for the Observability Layer (M4.1)."""

from __future__ import annotations

import pytest

from observability.tracing import ObservabilityCollector, SpanStatus


class TestObservabilityCollector:
    def test_start_trace_creates_trace(self) -> None:
        collector = ObservabilityCollector()
        trace = collector.start_trace("t1")
        assert trace.trace_id == "t1"
        assert trace.start_time is not None
        assert trace.end_time is None

    def test_start_trace_generates_uuid(self) -> None:
        collector = ObservabilityCollector()
        trace = collector.start_trace()
        assert trace.trace_id
        assert len(trace.trace_id) == 36

    def test_start_span_requires_trace(self) -> None:
        collector = ObservabilityCollector()
        with pytest.raises(ValueError):
            collector.start_span("missing", "span")

    def test_start_span_creates_span(self) -> None:
        collector = ObservabilityCollector()
        collector.start_trace("t1")
        span = collector.start_span("t1", "step-1")
        assert span.trace_id == "t1"
        assert span.name == "step-1"
        assert span.status == SpanStatus.OK
        assert span.end_time is None

    def test_root_span_set_automatically(self) -> None:
        collector = ObservabilityCollector()
        trace = collector.start_trace("t1")
        span = collector.start_span("t1", "root")
        assert trace.root_span_id == span.span_id

    def test_nested_spans(self) -> None:
        collector = ObservabilityCollector()
        collector.start_trace("t1")
        parent = collector.start_span("t1", "parent")
        child = collector.start_span("t1", "child", parent_id=parent.span_id)
        assert child.parent_id == parent.span_id
        children = collector.get_child_spans("t1", parent.span_id)
        assert len(children) == 1
        assert children[0].span_id == child.span_id

    def test_end_span(self) -> None:
        collector = ObservabilityCollector()
        collector.start_trace("t1")
        span = collector.start_span("t1", "s1")
        collector.end_span("t1", span.span_id, SpanStatus.ERROR)
        assert span.end_time is not None
        assert span.status == SpanStatus.ERROR

    def test_end_trace(self) -> None:
        collector = ObservabilityCollector()
        trace = collector.start_trace("t1")
        collector.end_trace("t1")
        assert trace.end_time is not None

    def test_span_duration(self) -> None:
        collector = ObservabilityCollector()
        collector.start_trace("t1")
        span = collector.start_span("t1", "s1")
        collector.end_span("t1", span.span_id)
        assert span.duration_ms() is not None
        assert span.duration_ms() >= 0

    def test_trace_duration(self) -> None:
        collector = ObservabilityCollector()
        trace = collector.start_trace("t1")
        collector.end_trace("t1")
        assert trace.duration_ms() is not None
        assert trace.duration_ms() >= 0

    def test_span_event(self) -> None:
        collector = ObservabilityCollector()
        collector.start_trace("t1")
        span = collector.start_span("t1", "s1")
        span.add_event("checkpoint", {"key": "value"})
        assert len(span.events) == 1
        assert span.events[0]["name"] == "checkpoint"
        assert span.events[0]["attributes"]["key"] == "value"

    def test_get_trace(self) -> None:
        collector = ObservabilityCollector()
        collector.start_trace("t1")
        assert collector.get_trace("t1") is not None
        assert collector.get_trace("missing") is None

    def test_list_traces(self) -> None:
        collector = ObservabilityCollector()
        collector.start_trace("t1")
        collector.start_trace("t2")
        assert len(collector.list_traces()) == 2

    def test_clear(self) -> None:
        collector = ObservabilityCollector()
        collector.start_trace("t1")
        collector.clear()
        assert collector.list_traces() == []
