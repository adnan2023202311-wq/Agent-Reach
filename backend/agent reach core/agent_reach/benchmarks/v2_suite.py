"""
Benchmark Suite V2 (M7.13).

Enhanced benchmarking for all Milestone 7 subsystems:
- Memory benchmarks (LongCat)
- Planning benchmarks
- Provider benchmarks
- MOA benchmarks
- Reflection benchmarks
- Skills benchmarks
- Context benchmarks
- Learning benchmarks

Builds on the existing BenchmarkSuite from Milestone 6.13.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from benchmarks import BenchmarkResult, run_benchmark


class BenchmarkCategory(str, Enum):
    MEMORY = "memory"
    PLANNING = "planning"
    PROVIDERS = "providers"
    MOA = "moa"
    REFLECTION = "reflection"
    SKILLS = "skills"
    CONTEXT = "context"
    LEARNING = "learning"


@dataclass
class BenchmarkReport:
    """Aggregated benchmark report for multiple categories."""
    title: str = ""
    results: list[BenchmarkResult] = field(default_factory=list)
    categories: dict[str, list[BenchmarkResult]] = field(default_factory=dict)
    summary: str = ""

    def add_result(self, result: BenchmarkResult, category: BenchmarkCategory) -> None:
        self.results.append(result)
        self.categories.setdefault(category.value, []).append(result)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "total_benchmarks": len(self.results),
            "categories": {
                cat: [r.to_dict() for r in results]
                for cat, results in self.categories.items()
            },
            "summary": self.summary,
        }


class BenchmarkSuiteV2:
    """Enhanced benchmark suite for Milestone 7 subsystems.

    Benchmarks each subsystem independently and produces aggregated reports.
    """

    def __init__(self) -> None:
        self._results: dict[str, list[BenchmarkResult]] = {}
        self._suite_start: float = 0.0

    # ------------------------------------------------------------------
    # Memory Benchmarks
    # ------------------------------------------------------------------

    @staticmethod
    def benchmark_memory_store(
        count: int = 1000,
    ) -> BenchmarkResult:
        """Benchmark memory storage throughput."""
        from memory.longcat import LongCatMemoryEngine

        engine = LongCatMemoryEngine()

        def _store() -> None:
            for i in range(count):
                engine.store(f"memory_item_{i}", importance=0.5)

        return run_benchmark(_store, name="memory_store", iterations=1)

    @staticmethod
    def benchmark_memory_retrieval(
        count: int = 500,
    ) -> BenchmarkResult:
        """Benchmark memory retrieval."""
        from memory.longcat import LongCatMemoryEngine

        engine = LongCatMemoryEngine()
        for i in range(count * 2):
            engine.store(f"memory_{i}", importance=0.1 + 0.8 * (i / (count * 2)))

        def _retrieve() -> None:
            for _ in range(10):
                engine.retrieve_relevant(count=20)

        return run_benchmark(_retrieve, name="memory_retrieval", iterations=5)

    @staticmethod
    def benchmark_memory_semantic_search(
        count: int = 200,
    ) -> BenchmarkResult:
        """Benchmark semantic memory search."""
        from memory.longcat import LongCatMemoryEngine

        engine = LongCatMemoryEngine()
        for i in range(count):
            engine.store(f"python programming concept number {i}", importance=0.5)

        def _search() -> None:
            engine.semantic_search("python programming", limit=10)

        return run_benchmark(_search, name="memory_semantic_search", iterations=5)

    @staticmethod
    def benchmark_memory_compression(
        count: int = 100,
    ) -> BenchmarkResult:
        """Benchmark memory compression."""
        from memory.longcat import LongCatMemoryEngine

        engine = LongCatMemoryEngine()
        ids = [engine.store(f"msg_{i}") for i in range(count)]

        def _compress() -> None:
            engine.compress_conversation(ids)

        return run_benchmark(_compress, name="memory_compression", iterations=3)

    # ------------------------------------------------------------------
    # Context Benchmarks
    # ------------------------------------------------------------------

    @staticmethod
    def benchmark_context_build(
        item_count: int = 200,
    ) -> BenchmarkResult:
        """Benchmark context window building."""
        from context.engine import ContextEngine

        engine = ContextEngine()
        for i in range(item_count):
            engine.add(f"context_item_{i}" * 5)

        def _build() -> None:
            engine.build(budget=8000)

        return run_benchmark(_build, name="context_build", iterations=10)

    @staticmethod
    def benchmark_context_compression(
        text_length: int = 10000,
    ) -> BenchmarkResult:
        """Benchmark context compression."""
        from context.engine import ContextCompressor

        compressor = ContextCompressor()
        text = "Lorem ipsum dolor sit amet. " * (text_length // 28)

        def _compress() -> None:
            compressor.compress(text, target_tokens=500)

        return run_benchmark(_compress, name="context_compression", iterations=20)

    # ------------------------------------------------------------------
    # Provider Benchmarks
    # ------------------------------------------------------------------

    @staticmethod
    def benchmark_router_scoring(
        iterations: int = 100,
    ) -> BenchmarkResult:
        """Benchmark router provider scoring."""
        from routing.router import ReachIntelligenceRouter

        router = ReachIntelligenceRouter()

        def _score() -> None:
            router.score_providers()

        return run_benchmark(_score, name="router_scoring", iterations=iterations)

    # ------------------------------------------------------------------
    # MOA Benchmarks
    # ------------------------------------------------------------------

    @staticmethod
    def benchmark_moa_strategy_creation(
        iterations: int = 100,
    ) -> BenchmarkResult:
        """Benchmark MOA strategy object creation."""
        from moa.engine import MOAStrategy, MOAExecutionMode

        def _create() -> None:
            MOAStrategy(
                mode=MOAExecutionMode.PARALLEL,
                providers=["anthropic", "openai", "gemini"],
                max_retries=2,
            )

        return run_benchmark(_create, name="moa_strategy", iterations=iterations)

    # ------------------------------------------------------------------
    # Reflection Benchmarks
    # ------------------------------------------------------------------

    @staticmethod
    def benchmark_reflection(
        iterations: int = 50,
    ) -> BenchmarkResult:
        """Benchmark reflection engine."""
        from reflection.v2_engine import ReflectionEngineV2
        from evaluation.engine import EvaluationReport, EvaluationResult

        engine = ReflectionEngineV2()
        report = EvaluationReport(results=[
            EvaluationResult(criterion_name=f"criterion_{i}", score=0.5 + 0.1 * i, passed=i < 4)
            for i in range(5)
        ])

        def _reflect() -> None:
            engine.reflect(report)

        return run_benchmark(_reflect, name="reflection", iterations=iterations)

    # ------------------------------------------------------------------
    # Skill Benchmarks
    # ------------------------------------------------------------------

    @staticmethod
    def benchmark_skill_discovery(
        skill_count: int = 200,
    ) -> BenchmarkResult:
        """Benchmark skill discovery."""
        from skills.ecosystem import SkillEcosystem, SkillMetadata
        from skills.engine import Skill

        async def _dummy(**kwargs: Any) -> str:
            return "ok"

        ecosystem = SkillEcosystem()
        for i in range(skill_count):
            cat = f"category_{i % 5}"
            skill = Skill(id=f"s{i}", name=f"skill_{i}", executor=_dummy)
            ecosystem.register(skill, metadata=SkillMetadata(category=cat, tags=[f"tag_{i % 3}"]))

        def _discover() -> None:
            ecosystem.discover(category="category_2")

        return run_benchmark(_discover, name="skill_discovery", iterations=10)

    # ------------------------------------------------------------------
    # Knowledge Graph Benchmarks
    # ------------------------------------------------------------------

    @staticmethod
    def benchmark_kg_traversal(
        node_count: int = 100,
    ) -> BenchmarkResult:
        """Benchmark knowledge graph traversal."""
        from knowledge.graph import KnowledgeGraph, NodeType, EdgeType

        kg = KnowledgeGraph()
        node_ids = []
        for i in range(node_count):
            nid = kg.add_node(NodeType.AGENT if i % 2 == 0 else NodeType.SKILL, f"node_{i}")
            node_ids.append(nid)
        for i in range(node_count - 1):
            kg.add_edge(node_ids[i], node_ids[i + 1], EdgeType.RELATED_TO)

        def _traverse() -> None:
            kg.traverse(node_ids[0], max_depth=5)

        return run_benchmark(_traverse, name="kg_traversal", iterations=10)

    # ------------------------------------------------------------------
    # Learning Benchmarks
    # ------------------------------------------------------------------

    @staticmethod
    def benchmark_learning_record(
        count: int = 500,
    ) -> BenchmarkResult:
        """Benchmark learning engine recording."""
        from learning.engine import ReachLearningEngine

        engine = ReachLearningEngine()

        def _record() -> None:
            for i in range(count):
                engine.record(
                    task=f"task_{i}",
                    provider=f"provider_{i % 4}",
                    quality=0.5 + 0.5 * (i / count),
                    latency_ms=100 + i,
                )

        return run_benchmark(_record, name="learning_record", iterations=1)

    # ------------------------------------------------------------------
    # Full Suite
    # ------------------------------------------------------------------

    def run_all(self) -> BenchmarkReport:
        """Run all benchmarks and produce a report."""
        report = BenchmarkReport(title="Agent-Reach Milestone 7 Benchmark Report")
        self._suite_start = time.time()

        # Memory benchmarks
        report.add_result(self.benchmark_memory_store(), BenchmarkCategory.MEMORY)
        report.add_result(self.benchmark_memory_retrieval(), BenchmarkCategory.MEMORY)
        report.add_result(self.benchmark_memory_semantic_search(), BenchmarkCategory.MEMORY)
        report.add_result(self.benchmark_memory_compression(), BenchmarkCategory.MEMORY)

        # Context benchmarks
        report.add_result(self.benchmark_context_build(), BenchmarkCategory.CONTEXT)
        report.add_result(self.benchmark_context_compression(), BenchmarkCategory.CONTEXT)

        # Provider benchmarks
        report.add_result(self.benchmark_router_scoring(), BenchmarkCategory.PROVIDERS)

        # MOA benchmarks
        report.add_result(self.benchmark_moa_strategy_creation(), BenchmarkCategory.MOA)

        # Reflection benchmarks
        report.add_result(self.benchmark_reflection(), BenchmarkCategory.REFLECTION)

        # Skills benchmarks
        report.add_result(self.benchmark_skill_discovery(), BenchmarkCategory.SKILLS)

        # Knowledge Graph benchmarks
        report.add_result(self.benchmark_kg_traversal(), BenchmarkCategory.LEARNING)

        # Learning benchmarks
        report.add_result(self.benchmark_learning_record(), BenchmarkCategory.LEARNING)

        total_time = time.time() - self._suite_start
        total_ops = sum(r.iterations for r in report.results)
        report.summary = (
            f"Total benchmarks: {len(report.results)}, "
            f"Total iterations: {total_ops}, "
            f"Total time: {total_time:.2f}s"
        )

        return report

    def get_category_results(self, category: BenchmarkCategory) -> list[BenchmarkResult]:
        """Get results for a specific category."""
        return self._results.get(category.value, [])

    def clear(self) -> None:
        """Clear all benchmark results."""
        self._results.clear()
        self._suite_start = 0.0
