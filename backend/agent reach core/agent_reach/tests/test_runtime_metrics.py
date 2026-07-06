"""Tests for Runtime Metrics (M4.2)."""

from __future__ import annotations

import pytest

from observability.metrics import MetricsCollector


class TestMetricsCollector:
    def test_counter_records_value(self) -> None:
        collector = MetricsCollector()
        collector.counter("requests", 1.0, {"route": "/health"})
        values = collector.get_values("requests")
        assert len(values) == 1
        assert values[0].value == 1.0
        assert values[0].labels == {"route": "/health"}

    def test_counter_default_value(self) -> None:
        collector = MetricsCollector()
        collector.counter("events")
        values = collector.get_values("events")
        assert len(values) == 1
        assert values[0].value == 1.0

    def test_gauge_records_value(self) -> None:
        collector = MetricsCollector()
        collector.gauge("memory_usage", 512.0)
        values = collector.get_values("memory_usage")
        assert len(values) == 1
        assert values[0].value == 512.0

    def test_histogram_records_value(self) -> None:
        collector = MetricsCollector()
        collector.histogram("latency", 42.0)
        values = collector.get_values("latency")
        assert len(values) == 1
        assert values[0].value == 42.0

    def test_multiple_observations(self) -> None:
        collector = MetricsCollector()
        collector.counter("requests", 1.0)
        collector.counter("requests", 2.0)
        agg = collector.get_aggregated("requests")
        assert agg["count"] == 2
        assert agg["sum"] == 3.0
        assert agg["avg"] == 1.5

    def test_aggregated_min_max(self) -> None:
        collector = MetricsCollector()
        collector.histogram("latency", 10.0)
        collector.histogram("latency", 20.0)
        collector.histogram("latency", 30.0)
        agg = collector.get_aggregated("latency")
        assert agg["min"] == 10.0
        assert agg["max"] == 30.0

    def test_aggregated_empty(self) -> None:
        collector = MetricsCollector()
        agg = collector.get_aggregated("missing")
        assert agg["count"] == 0
        assert agg["sum"] == 0.0

    def test_get_metrics_returns_copy(self) -> None:
        collector = MetricsCollector()
        collector.counter("x", 1.0)
        metrics = collector.get_metrics()
        metrics["x"].clear()
        assert len(collector.get_values("x")) == 1

    def test_clear(self) -> None:
        collector = MetricsCollector()
        collector.counter("x", 1.0)
        collector.clear()
        assert collector.get_values("x") == []
