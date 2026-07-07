"""
Benchmarks layer: Benchmark Suite (M6.13).

Layer: Application/Core — depends inward on all layers.

Provides benchmarking utilities to measure:
- workflow latency (time to execute a workflow)
- planner latency (time to create a plan)
- provider latency (time for a model call)
- memory usage (peak memory during operations)
- startup time (time to build the application)

Benchmarks are synchronous functions that return a BenchmarkResult
with timing data. They are designed to be run from tests or a CLI,
not in the hot path of the application.

Design notes
------------
- Each benchmark is a self-contained function that sets up its own
  fixtures, runs the operation, and returns timing data.
- Memory usage is measured using tracemalloc (if available) or
  resource module (Unix only). If neither is available, memory
  stats are reported as None.
- Benchmarks are deterministic where possible: they use fake agents
  and mock model clients to avoid network variance.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run.

    Attributes:
        name: benchmark name.
        duration_ms: wall-clock duration in milliseconds.
        iterations: number of iterations run.
        avg_ms: average duration per iteration.
        min_ms: minimum duration.
        max_ms: maximum duration.
        peak_memory_bytes: peak memory usage (None if unavailable).
        metadata: arbitrary additional data.
    """

    name: str = ""
    duration_ms: float = 0.0
    iterations: int = 1
    avg_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    peak_memory_bytes: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "name": self.name,
            "duration_ms": self.duration_ms,
            "iterations": self.iterations,
            "avg_ms": self.avg_ms,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
            "peak_memory_bytes": self.peak_memory_bytes,
            "metadata": dict(self.metadata),
        }


def run_benchmark(
    func: Callable[[], Any],
    *,
    name: str = "",
    iterations: int = 1,
    warmup: int = 0,
    measure_memory: bool = True,
) -> BenchmarkResult:
    """Run a function multiple times and collect timing statistics.

    Parameters
    ----------
    func:
        The function to benchmark. Called with no arguments.
    name:
        Name for the benchmark.
    iterations:
        Number of timed iterations.
    warmup:
        Number of untimed warmup iterations (to warm caches, JIT, etc.).
    measure_memory:
        Whether to measure peak memory usage.

    Returns
    -------
    BenchmarkResult with timing statistics.
    """
    # Warmup phase.
    for _ in range(warmup):
        func()

    # Memory measurement setup.
    tracker: Any = None
    if measure_memory:
        try:
            import tracemalloc
            tracemalloc.start()
            tracker = tracemalloc
        except ImportError:
            pass

    # Timed iterations.
    times: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append((end - start) * 1000.0)  # Convert to ms.

    # Memory measurement teardown.
    peak_memory: Optional[int] = None
    if tracker is not None:
        try:
            _, peak = tracker.get_traced_memory()
            peak_memory = int(peak)
            tracker.stop()
        except Exception:
            pass

    total = sum(times)
    return BenchmarkResult(
        name=name or func.__name__,
        duration_ms=total,
        iterations=iterations,
        avg_ms=total / iterations if iterations > 0 else 0.0,
        min_ms=min(times) if times else 0.0,
        max_ms=max(times) if times else 0.0,
        peak_memory_bytes=peak_memory,
        metadata={},
    )
