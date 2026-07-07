"""Tests for M7.9-M7.13: Adaptive Execution, Learning Engine, Tutti, MCP Intelligence, Benchmark V2."""
from __future__ import annotations

import json

import pytest

# M7.9
from adaptive.execution import (
    AdaptiveExecutor,
    AdaptiveResult,
    ExecutionBudget,
    ExecutionConfig,
    ExecutionMode,
)

# M7.10
from learning.engine import (
    ExecutionRecord,
    ProviderLearning,
    ReachLearningEngine,
    Recommendation,
)

# M7.11
from tutti.exporter import PortableContext, TargetPlatform, TuttiExporter

# M7.12
from mcp.intelligence import MCPIntelligence, ToolRankingMethod, ToolStats
from mcp.runtime import MCPToolDefinition, MCPRequest

# M7.13
from benchmarks.v2_suite import BenchmarkCategory, BenchmarkReport, BenchmarkSuiteV2
from benchmarks import BenchmarkResult


# ===========================================================================
# M7.9 Adaptive Execution
# ===========================================================================

class TestAdaptiveExecutor:
    def test_select_mode_fast_for_simple(self) -> None:
        executor = AdaptiveExecutor()
        mode = executor.select_mode(task_complexity=0.2)
        assert mode == ExecutionMode.FAST

    def test_select_mode_max_quality_for_complex(self) -> None:
        executor = AdaptiveExecutor()
        mode = executor.select_mode(task_complexity=0.9)
        assert mode == ExecutionMode.MAXIMUM_QUALITY

    def test_select_mode_balanced_for_medium(self) -> None:
        executor = AdaptiveExecutor()
        mode = executor.select_mode(task_complexity=0.5)
        assert mode == ExecutionMode.BALANCED

    def test_select_mode_user_preference(self) -> None:
        executor = AdaptiveExecutor()
        mode = executor.select_mode(task_complexity=0.9, user_preference=ExecutionMode.FAST)
        assert mode == ExecutionMode.FAST

    def test_build_config_fast(self) -> None:
        executor = AdaptiveExecutor()
        config = executor.build_config(ExecutionMode.FAST, task_complexity=0.2)
        assert config.mode == ExecutionMode.FAST
        assert config.prefer_cheap
        assert config.max_retries == 0
        assert config.quality_threshold == 0.3

    def test_build_config_max_quality(self) -> None:
        executor = AdaptiveExecutor()
        config = executor.build_config(ExecutionMode.MAXIMUM_QUALITY, task_complexity=0.9)
        assert config.mode == ExecutionMode.MAXIMUM_QUALITY
        assert not config.prefer_cheap
        assert config.max_retries == 2
        assert config.quality_threshold == 0.6

    def test_should_retry_low_quality(self) -> None:
        executor = AdaptiveExecutor()
        result = AdaptiveResult(quality_score=0.3, retries=0)
        config = ExecutionConfig(mode=ExecutionMode.BALANCED, max_retries=2, quality_threshold=0.6)
        assert executor.should_retry(result, config)

    def test_should_not_retry_good_quality(self) -> None:
        executor = AdaptiveExecutor()
        result = AdaptiveResult(quality_score=0.8, retries=0)
        config = ExecutionConfig(mode=ExecutionMode.BALANCED, max_retries=2, quality_threshold=0.6)
        assert not executor.should_retry(result, config)

    def test_should_not_retry_max_reached(self) -> None:
        executor = AdaptiveExecutor()
        result = AdaptiveResult(quality_score=0.3, retries=2)
        config = ExecutionConfig(mode=ExecutionMode.BALANCED, max_retries=2, quality_threshold=0.6)
        assert not executor.should_retry(result, config)

    def test_retry_strategy_different_provider(self) -> None:
        executor = AdaptiveExecutor()
        result = AdaptiveResult(quality_score=0.2)
        config = ExecutionConfig()
        strategy = executor.select_retry_strategy(result, config)
        assert strategy == "different_provider"

    def test_record_and_get_stats(self) -> None:
        executor = AdaptiveExecutor()
        executor.record_result(AdaptiveResult(
            mode_used=ExecutionMode.FAST,
            provider_used="test",
            quality_score=0.8,
            cost=0.01,
            latency_ms=100,
        ))
        executor.record_result(AdaptiveResult(
            mode_used=ExecutionMode.FAST,
            provider_used="test",
            quality_score=0.6,
            cost=0.01,
            latency_ms=150,
        ))
        stats = executor.get_mode_stats()
        assert stats["fast"]["count"] == 2
        assert stats["fast"]["avg_quality"] == 0.7

    def test_get_recommendation(self) -> None:
        executor = AdaptiveExecutor()
        rec = executor.get_recommendation(task_complexity=0.3)
        assert "recommended_mode" in rec
        assert "strategy" in rec

    def test_clear(self) -> None:
        executor = AdaptiveExecutor()
        executor.record_result(AdaptiveResult(mode_used=ExecutionMode.FAST, provider_used="x"))
        executor.clear()
        stats = executor.get_mode_stats()
        assert stats["fast"]["count"] == 0


class TestExecutionBudget:
    def test_default(self) -> None:
        budget = ExecutionBudget()
        assert budget.mode == ExecutionMode.BALANCED
        assert budget.max_cost == float("inf")


class TestExecutionConfig:
    def test_default(self) -> None:
        config = ExecutionConfig()
        assert config.mode == ExecutionMode.BALANCED
        assert config.max_retries == 2


# ===========================================================================
# M7.10 Reach Learning Engine
# ===========================================================================

class TestReachLearningEngine:
    def test_record_execution(self) -> None:
        engine = ReachLearningEngine()
        engine.record(
            task="Summarize this article about AI",
            provider="anthropic",
            quality=0.9,
            latency_ms=500,
        )
        stats = engine.get_stats()
        assert stats["total_executions"] == 1
        assert stats["success_rate"] == 1.0

    def test_record_failed_execution(self) -> None:
        engine = ReachLearningEngine()
        engine.record(task="buggy code", provider="openai", success=False, quality=0.0)
        stats = engine.get_stats()
        assert stats["success_rate"] == 0.0

    def test_get_provider_learning(self) -> None:
        engine = ReachLearningEngine()
        for i in range(5):
            engine.record(
                task=f"task_{i}",
                provider="anthropic",
                quality=0.8,
                latency_ms=200,
                cost=0.01,
            )
        pl = engine.get_provider_learning("anthropic")
        assert pl.total_executions == 5
        assert pl.success_rate == 1.0
        assert pl.avg_quality == 0.8

    def test_compare_providers(self) -> None:
        engine = ReachLearningEngine()
        engine.record(task="task a", provider="openai", quality=0.9)
        engine.record(task="task b", provider="anthropic", quality=0.7)
        comparison = engine.compare_providers()
        assert "openai" in comparison
        assert "anthropic" in comparison

    def test_best_provider_for(self) -> None:
        engine = ReachLearningEngine()
        for _ in range(5):
            engine.record(task="summarize doc", provider="anthropic", quality=0.9)
        for _ in range(5):
            engine.record(task="summarize doc", provider="openai", quality=0.6)
        best = engine.best_provider_for("summarization")
        assert best is not None

    def test_generate_recommendations(self) -> None:
        engine = ReachLearningEngine()
        for i in range(10):
            engine.record(task=f"task_{i}", provider="anthropic", quality=0.8, mode="balanced")
        recs = engine.generate_recommendations()
        assert len(recs) > 0

    def test_suggest_optimization_providers(self) -> None:
        engine = ReachLearningEngine()
        for _ in range(10):
            engine.record(task="test", provider="bad_provider", success=False)
        suggestions = engine.suggest_optimization("providers")
        assert len(suggestions) > 0

    def test_suggest_optimization_cost(self) -> None:
        engine = ReachLearningEngine()
        engine.record(task="test", provider="expensive", cost=0.5)
        engine.record(task="test", provider="cheap", cost=0.001)
        suggestions = engine.suggest_optimization("cost")
        assert len(suggestions) > 0

    def test_get_learning_cache(self) -> None:
        engine = ReachLearningEngine()
        engine.record(task="test", provider="anthropic")
        cache = engine.get_learning_cache()
        assert "generation" in cache
        assert "provider_stats" in cache

    def test_evolve(self) -> None:
        engine = ReachLearningEngine()
        engine.record(task="test", provider="anthropic")
        engine.evolve()
        cache = engine.get_learning_cache()
        assert cache["generation"] == 1

    def test_infer_task_type(self) -> None:
        assert ReachLearningEngine._infer_task_type("summarize the document") == "summarization"
        assert ReachLearningEngine._infer_task_type("write code for API") == "coding"
        assert ReachLearningEngine._infer_task_type("what is Python?") == "question"
        assert ReachLearningEngine._infer_task_type("random text here") == "general"

    def test_clear(self) -> None:
        engine = ReachLearningEngine()
        engine.record(task="test", provider="anthropic")
        engine.clear()
        assert engine.get_stats()["total_executions"] == 0


class TestExecutionRecord:
    def test_default(self) -> None:
        record = ExecutionRecord(task="test", provider="anthropic")
        assert record.task == "test"
        assert record.success


class TestRecommendation:
    def test_default(self) -> None:
        rec = Recommendation(category="provider", recommendation="use X", confidence=0.8, based_on=50)
        assert rec.category == "provider"
        assert rec.confidence == 0.8


# ===========================================================================
# M7.11 Tutti Context Export
# ===========================================================================

class TestPortableContext:
    def test_to_dict(self) -> None:
        ctx = PortableContext(
            system_prompt="Be helpful",
            conversation=[{"role": "user", "content": "hi"}],
        )
        d = ctx.to_dict()
        assert d["system_prompt"] == "Be helpful"
        assert len(d["conversation"]) == 1

    def test_to_json(self) -> None:
        ctx = PortableContext(system_prompt="test")
        json_str = ctx.to_json()
        assert "test" in json_str

    def test_from_json(self) -> None:
        ctx = PortableContext(system_prompt="test")
        json_str = ctx.to_json()
        ctx2 = PortableContext.from_json(json_str)
        assert ctx2.system_prompt == "test"

    def test_from_dict(self) -> None:
        d = {
            "system_prompt": "hello",
            "target_platform": "chatgpt",
            "conversation": [],
        }
        ctx = PortableContext.from_dict(d)
        assert ctx.system_prompt == "hello"
        assert ctx.target_platform == TargetPlatform.CHATGPT

    def test_roundtrip(self) -> None:
        ctx = PortableContext(
            system_prompt="Be helpful.",
            conversation=[{"role": "user", "content": "hello"}],
            memories=[{"content": "user likes Python"}],
            metadata={"session_id": "s1"},
        )
        json_str = ctx.to_json()
        restored = PortableContext.from_json(json_str)
        assert restored.system_prompt == ctx.system_prompt
        assert restored.conversation == ctx.conversation
        assert restored.memories == ctx.memories


class TestTuttiExporter:
    def test_export_context(self) -> None:
        exporter = TuttiExporter()
        ctx = exporter.export_context(
            target=TargetPlatform.GENERIC,
            system_prompt="Be helpful",
            conversation=[{"role": "user", "content": "hello"}],
        )
        assert ctx is not None
        assert ctx.system_prompt == "Be helpful"

    def test_export_to_json(self) -> None:
        exporter = TuttiExporter()
        json_str = exporter.export_to_json(
            target=TargetPlatform.GENERIC,
            system_prompt="test",
        )
        assert "test" in json_str

    def test_import_context_from_dict(self) -> None:
        exporter = TuttiExporter()
        ctx = exporter.import_context({
            "system_prompt": "imported",
            "target_platform": "generic",
        })
        assert ctx.system_prompt == "imported"

    def test_import_context_from_json(self) -> None:
        exporter = TuttiExporter()
        ctx = PortableContext(system_prompt="imported")
        ctx2 = exporter.import_context(ctx.to_json())
        assert ctx2.system_prompt == "imported"

    def test_import_for_resume(self) -> None:
        exporter = TuttiExporter()
        ctx = PortableContext(
            system_prompt="resume me",
            conversation=[{"role": "user", "content": "continue"}],
            memories=[{"content": "context"}],
        )
        resume = exporter.import_for_resume(ctx.to_json())
        assert resume["system_prompt"] == "resume me"
        assert "context_id" in resume

    def test_convert_for_platform(self) -> None:
        exporter = TuttiExporter()
        ctx = PortableContext(
            system_prompt="original",
            memories=[{"content": "memory text"}],
        )
        converted = exporter.convert_for_platform(ctx, TargetPlatform.CHATGPT)
        assert converted.target_platform == TargetPlatform.CHATGPT
        assert converted.metadata.get("format") == "openai_chat"

    def test_create_resume_package(self) -> None:
        exporter = TuttiExporter()
        pkg = exporter.create_resume_package(
            session_id="s123",
            conversation=[{"role": "user", "content": "resume"}],
            system_prompt="resume session",
        )
        assert pkg.metadata.get("session_id") == "s123"
        assert pkg.metadata.get("resume") is True

    def test_list_exports(self) -> None:
        exporter = TuttiExporter()
        exporter.export_context(system_prompt="one")
        exporter.export_context(system_prompt="two")
        exports = exporter.list_exports()
        assert len(exports) == 2

    def test_get_export(self) -> None:
        exporter = TuttiExporter()
        ctx = exporter.export_context(system_prompt="find me")
        retrieved = exporter.get_export(ctx.id)
        assert retrieved is not None
        assert retrieved.system_prompt == "find me"

    def test_clear(self) -> None:
        exporter = TuttiExporter()
        exporter.export_context(system_prompt="x")
        exporter.clear()
        assert len(exporter.list_exports()) == 0

    def test_all_target_platforms(self) -> None:
        exporter = TuttiExporter()
        for platform in TargetPlatform:
            ctx = exporter.export_context(target=platform, system_prompt=f"for {platform.value}")
            assert ctx.target_platform == platform


# ===========================================================================
# M7.12 MCP Intelligence
# ===========================================================================

class TestMCPIntelligence:
    @pytest.mark.asyncio
    async def test_register_with_capabilities(self) -> None:
        mcp = MCPIntelligence()
        async def _tool(req: MCPRequest) -> str:
            return "ok"
        tool_def = MCPToolDefinition(name="search", description="web search")
        mcp.register_tool(tool_def, _tool, capability_tags=["web_search", "information"])
        assert mcp.runtime.has_tool("search")

    @pytest.mark.asyncio
    async def test_discover_by_capability(self) -> None:
        mcp = MCPIntelligence()
        async def _tool(req: MCPRequest) -> str:
            return "ok"
        mcp.register_tool(
            MCPToolDefinition(name="search"), _tool, capability_tags=["web_search"]
        )
        mcp.register_tool(
            MCPToolDefinition(name="calc"), _tool, capability_tags=["calculation"]
        )
        results = mcp.discover_by_capability(["web_search"])
        assert len(results) == 1
        assert results[0].name == "search"

    def test_detect_capabilities(self) -> None:
        mcp = MCPIntelligence()
        caps = mcp.detect_capabilities("search the web for AI news")
        assert "web_search" in caps

    def test_detect_capabilities_coding(self) -> None:
        mcp = MCPIntelligence()
        caps = mcp.detect_capabilities("run python code to calculate sum")
        assert "code_execution" in caps or "calculation" in caps

    @pytest.mark.asyncio
    async def test_rank_tools(self) -> None:
        mcp = MCPIntelligence()
        async def _tool(req: MCPRequest) -> str:
            return "ok"
        mcp.register_tool(MCPToolDefinition(name="a"), _tool)
        mcp.register_tool(MCPToolDefinition(name="b"), _tool)
        rankings = mcp.rank_tools()
        assert len(rankings) == 2
        assert rankings[0].rank == 1
        assert rankings[1].rank == 2

    @pytest.mark.asyncio
    async def test_recommend_tools(self) -> None:
        mcp = MCPIntelligence()
        async def _tool(req: MCPRequest) -> str:
            return "ok"
        mcp.register_tool(
            MCPToolDefinition(name="search"), _tool, capability_tags=["web_search"]
        )
        mcp.register_tool(
            MCPToolDefinition(name="calc"), _tool, capability_tags=["calculation"]
        )
        recs = mcp.recommend_tools("search the internet for dogs")
        assert any(r.definition.name == "search" for r in recs)

    @pytest.mark.asyncio
    async def test_select_tool(self) -> None:
        mcp = MCPIntelligence()
        async def _tool(req: MCPRequest) -> str:
            return "ok"
        mcp.register_tool(
            MCPToolDefinition(name="search"), _tool, capability_tags=["web_search"]
        )
        tool = mcp.select_tool("search the web")
        assert tool is not None
        assert tool.name == "search"

    @pytest.mark.asyncio
    async def test_execute_records_stats(self) -> None:
        mcp = MCPIntelligence()
        async def _tool(req: MCPRequest) -> str:
            return f"result: {req.parameters}"
        mcp.register_tool(MCPToolDefinition(name="echo"), _tool)

        request = MCPRequest(tool_name="echo", parameters={"msg": "hello"})
        response = await mcp.execute(request)
        assert response.success
        stats = mcp.get_tool_stats("echo")
        assert stats is not None
        assert stats.total_calls == 1
        assert stats.successes == 1

    @pytest.mark.asyncio
    async def test_benchmark_tool(self) -> None:
        mcp = MCPIntelligence()
        async def _tool(req: MCPRequest) -> str:
            return "ok"
        mcp.register_tool(MCPToolDefinition(name="fast"), _tool)
        benchmark = await mcp.benchmark_tool("fast", {"input": "test"}, runs=3)
        assert benchmark.runs == 3
        assert benchmark.success_rate >= 0.0

    def test_get_stats(self) -> None:
        mcp = MCPIntelligence()
        stats = mcp.get_stats()
        assert stats["total_tools"] == 0
        assert stats["total_calls"] == 0

    def test_clear(self) -> None:
        mcp = MCPIntelligence()
        async def _tool(req: MCPRequest) -> str:
            return "ok"
        mcp.register_tool(MCPToolDefinition(name="test"), _tool)
        mcp.clear()
        assert not mcp.runtime.has_tool("test")


class TestToolStats:
    def test_default(self) -> None:
        stats = ToolStats(tool_name="test")
        assert stats.tool_name == "test"
        assert stats.success_rate == 0.0


# ===========================================================================
# M7.13 Benchmark Suite V2
# ===========================================================================

class TestBenchmarkSuiteV2:
    def test_memory_store_benchmark(self) -> None:
        result = BenchmarkSuiteV2.benchmark_memory_store(count=50)
        assert result.name == "memory_store"
        assert result.duration_ms >= 0

    def test_memory_retrieval_benchmark(self) -> None:
        result = BenchmarkSuiteV2.benchmark_memory_retrieval(count=50)
        assert result.name == "memory_retrieval"

    def test_memory_semantic_search_benchmark(self) -> None:
        result = BenchmarkSuiteV2.benchmark_memory_semantic_search(count=30)
        assert result.name == "memory_semantic_search"

    def test_memory_compression_benchmark(self) -> None:
        result = BenchmarkSuiteV2.benchmark_memory_compression(count=20)
        assert result.name == "memory_compression"

    def test_context_build_benchmark(self) -> None:
        result = BenchmarkSuiteV2.benchmark_context_build(item_count=30)
        assert result.name == "context_build"

    def test_context_compression_benchmark(self) -> None:
        result = BenchmarkSuiteV2.benchmark_context_compression(text_length=200)
        assert result.name == "context_compression"

    def test_router_scoring_benchmark(self) -> None:
        result = BenchmarkSuiteV2.benchmark_router_scoring(iterations=10)
        assert result.name == "router_scoring"

    def test_moa_strategy_benchmark(self) -> None:
        result = BenchmarkSuiteV2.benchmark_moa_strategy_creation(iterations=10)
        assert result.name == "moa_strategy"

    def test_reflection_benchmark(self) -> None:
        result = BenchmarkSuiteV2.benchmark_reflection(iterations=10)
        assert result.name == "reflection"

    def test_skill_discovery_benchmark(self) -> None:
        result = BenchmarkSuiteV2.benchmark_skill_discovery(skill_count=20)
        assert result.name == "skill_discovery"

    def test_kg_traversal_benchmark(self) -> None:
        result = BenchmarkSuiteV2.benchmark_kg_traversal(node_count=20)
        assert result.name == "kg_traversal"

    def test_learning_record_benchmark(self) -> None:
        result = BenchmarkSuiteV2.benchmark_learning_record(count=30)
        assert result.name == "learning_record"

    def test_run_all(self) -> None:
        suite = BenchmarkSuiteV2()
        report = suite.run_all()
        assert report.title == "Agent-Reach Milestone 7 Benchmark Report"
        assert len(report.results) > 0
        assert report.summary

    def test_report_to_dict(self) -> None:
        report = BenchmarkReport(title="Test Report")
        report.add_result(
            BenchmarkResult(name="test", duration_ms=100, iterations=1, avg_ms=100, min_ms=100, max_ms=100),
            BenchmarkCategory.MEMORY,
        )
        d = report.to_dict()
        assert d["title"] == "Test Report"
        assert "memory" in d["categories"]


class TestBenchmarkCategory:
    def test_all_categories_exist(self) -> None:
        for cat in BenchmarkCategory:
            assert cat.value in (
                "memory", "planning", "providers", "moa",
                "reflection", "skills", "context", "learning",
            )
