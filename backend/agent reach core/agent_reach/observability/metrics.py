"""
Runtime Metrics: in-process metrics collection.

Inspired by Phoenix runtime diagnostics, but native and in-memory.
Supports counters, gauges, and histograms with label dimensions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricValue:
    """A single metric observation."""

    name: str
    value: float
    timestamp: float
    labels: dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """In-memory collector for runtime metrics.

    Every execution should produce metrics. The collector stores
    observations in memory for the lifetime of the process.
    """

    def __init__(self) -> None:
        self._metrics: dict[str, list[MetricValue]] = {}

    def counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Increment a counter metric."""
        self._record(name, value, labels)

    def gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a gauge metric (point-in-time value)."""
        self._record(name, value, labels)

    def histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a histogram observation (e.g., latency)."""
        self._record(name, value, labels)

    def _record(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        observation = MetricValue(
            name=name,
            value=value,
            timestamp=time.perf_counter(),
            labels=labels or {},
        )
        self._metrics.setdefault(name, []).append(observation)

    def get_metrics(self) -> dict[str, list[MetricValue]]:
        """Return all recorded metrics."""
        return {k: list(v) for k, v in self._metrics.items()}

    def get_values(self, name: str) -> list[MetricValue]:
        """Return all observations for a metric name."""
        return list(self._metrics.get(name, []))

    def get_aggregated(self, name: str) -> dict[str, Any]:
        """Return aggregated statistics for a metric name."""
        values = [m.value for m in self._metrics.get(name, [])]
        if not values:
            return {"count": 0, "sum": 0.0, "min": 0.0, "max": 0.0, "avg": 0.0}
        return {
            "count": len(values),
            "sum": sum(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
        }

    def clear(self) -> None:
        """Remove all metrics. Useful for testing."""
        self._metrics.clear()
