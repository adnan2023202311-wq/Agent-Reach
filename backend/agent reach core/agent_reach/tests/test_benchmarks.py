"""Unit tests for benchmarks module (M6.13)."""

from __future__ import annotations

import time

import pytest

from benchmarks import BenchmarkResult, run_benchmark


class TestBenchmarkResult:
    def test_to_dict(self) -> None:
        result = BenchmarkResult(
            name="test",
            duration_ms=100.0,
            iterations=5,
            avg_ms=20.0,
            min_ms=15.0,
            max_ms=25.0,
            peak_memory_bytes=1024,
        )
        d = result.to_dict()
        assert d["name"] == "test"
        assert d["duration_ms"] == 100.0
        assert d["iterations"] == 5
        assert d["avg_ms"] == 20.0
        assert d["peak_memory_bytes"] == 1024


class TestRunBenchmark:
    def test_single_iteration(self) -> None:
        def dummy() -> None:
            pass

        result = run_benchmark(dummy, name="dummy", iterations=1, measure_memory=False)
        assert result.name == "dummy"
        assert result.iterations == 1
        assert result.duration_ms >= 0

    def test_multiple_iterations(self) -> None:
        def dummy() -> None:
            pass

        result = run_benchmark(dummy, name="dummy", iterations=5, measure_memory=False)
        assert result.iterations == 5
        assert result.avg_ms == result.duration_ms / 5
        assert result.min_ms <= result.avg_ms <= result.max_ms

    def test_warmup(self) -> None:
        call_count = 0

        def counting_dummy() -> None:
            nonlocal call_count
            call_count += 1

        result = run_benchmark(
            counting_dummy, name="test", iterations=3, warmup=2, measure_memory=False
        )
        # 2 warmup + 3 timed = 5 total calls.
        assert call_count == 5
        assert result.iterations == 3

    def test_function_name_default(self) -> None:
        def my_func() -> None:
            pass

        result = run_benchmark(my_func, iterations=1, measure_memory=False)
        assert result.name == "my_func"

    def test_memory_measurement(self) -> None:
        def allocate() -> list[int]:
            return list(range(1000))

        result = run_benchmark(allocate, name="alloc", iterations=1, measure_memory=True)
        # Memory measurement may or may not be available depending on
        # the environment — just verify the benchmark completes.
        assert result.duration_ms >= 0
