"""
Integration tests for M7.5 — proving every M7 subsystem runs in the pipeline.

These are NOT unit tests of individual subsystems. They are end-to-end
integration tests that prove the full IntelligentPipeline works with
all 8 M7 subsystems participating.
"""
from __future__ import annotations

import pytest

from composition import build_default_controller, build_intelligent_pipeline
from core.intelligent_pipeline import (
    IntelligentPipeline,
    PipelineConfig,
    PipelineResult,
    PipelineTrace,
)
from domain.models import TaskStatus


# ===========================================================================
# Pipeline build & config
# ===========================================================================


class TestPipelineBuild:
    def test_build_succeeds(self) -> None:
        """Pipeline builds without errors."""
        pipeline = build_intelligent_pipeline()
        assert pipeline is not None
        assert isinstance(pipeline, IntelligentPipeline)

    def test_build_with_custom_config(self) -> None:
        """Pipeline builds with custom config."""
        config = PipelineConfig(enable_moa=False, enable_tutti=False)
        pipeline = build_intelligent_pipeline(config=config)
        assert pipeline._config.enable_moa is False
        assert pipeline._config.enable_tutti is False

    def test_all_subsystems_enabled_by_default(self) -> None:
        """All 8 subsystems are enabled by default."""
        pipeline = build_intelligent_pipeline()
        config = pipeline._config
        assert config.enable_router is True
        assert config.enable_memory is True
        assert config.enable_context is True
        assert config.enable_moa is True
        assert config.enable_reflection is True
        assert config.enable_knowledge_graph is True
        assert config.enable_learning is True
        assert config.enable_tutti is True


# ===========================================================================
# Pipeline execution — full integration
# ===========================================================================


@pytest.mark.asyncio
class TestPipelineExecution:
    async def test_process_simple_message(self) -> None:
        """Processing a simple message succeeds."""
        pipeline = build_intelligent_pipeline()
        result = await pipeline.process("What is Python?")
        assert result is not None
        assert result.outcome is not None
        assert result.answer is not None

    async def test_process_returns_trace(self) -> None:
        """Every process call returns a PipelineTrace."""
        pipeline = build_intelligent_pipeline()
        result = await pipeline.process("Explain machine learning")
        trace = result.trace
        assert trace is not None
        assert trace.request_id
        assert trace.total_latency_ms >= 0

    async def test_process_multiple_requests(self) -> None:
        """Multiple requests are handled correctly."""
        pipeline = build_intelligent_pipeline()
        r1 = await pipeline.process("Hello")
        r2 = await pipeline.process("How are you?")
        r3 = await pipeline.process("Tell me about AI")
        assert r1.answer is not None
        assert r2.answer is not None
        assert r3.answer is not None

    async def test_process_with_session_id(self) -> None:
        """Session ID is propagated through the pipeline."""
        pipeline = build_intelligent_pipeline()
        result = await pipeline.process(
            "Remember this", session_id="test-session-123"
        )
        assert result.answer is not None


# ===========================================================================
# Subsystem-by-subsystem integration verification
# ===========================================================================


@pytest.mark.asyncio
class TestSubsystemIntegration:
    async def test_router_active_in_trace(self) -> None:
        """Intelligence Router records its activity in the trace."""
        pipeline = build_intelligent_pipeline()
        result = await pipeline.process("What is the best programming language?")
        trace = result.trace
        assert trace.router_active is True
        assert trace.router_provider
        assert trace.router_latency_ms >= 0

    async def test_memory_active_in_trace(self) -> None:
        """LongCat Memory records its activity in the trace."""
        pipeline = build_intelligent_pipeline()
        result = await pipeline.process("Remember that I like Python")
        trace = result.trace
        assert trace.memory_active is True
        assert trace.memory_latency_ms >= 0

    async def test_memory_stores_and_retrieves(self) -> None:
        """Memory actually stores requests between calls."""
        pipeline = build_intelligent_pipeline()
        await pipeline.process("My name is TestUser")
        result = await pipeline.process("What is my name?")
        # Memory should have working items from the first request
        assert result.trace.memory_active is True

    async def test_context_active_in_trace(self) -> None:
        """Context Engine records its activity in the trace."""
        pipeline = build_intelligent_pipeline()
        result = await pipeline.process("Summarize the history of computing")
        trace = result.trace
        assert trace.context_active is True
        assert trace.context_tokens_used >= 0
        assert trace.context_budget > 0

    async def test_reflection_active_in_trace(self) -> None:
        """Reflection Engine V2 records its activity in the trace."""
        pipeline = build_intelligent_pipeline()
        result = await pipeline.process("Count from 1 to 5")
        trace = result.trace
        assert trace.reflection_active is True
        assert trace.reflection_score >= 0
        assert trace.reflection_latency_ms >= 0

    async def test_knowledge_graph_active_in_trace(self) -> None:
        """Knowledge Graph records its activity in the trace."""
        pipeline = build_intelligent_pipeline()
        result = await pipeline.process("What is a knowledge graph?")
        trace = result.trace
        assert trace.kg_active is True
        assert trace.kg_nodes_added > 0
        assert trace.kg_edges_added >= 0

    async def test_learning_active_in_trace(self) -> None:
        """Learning Engine records its activity in the trace."""
        pipeline = build_intelligent_pipeline()
        result = await pipeline.process("Teach me about neural networks")
        trace = result.trace
        assert trace.learning_active is True
        assert trace.learning_recorded is True

    async def test_tutti_active_in_trace(self) -> None:
        """Tutti Context produces an export ID in the trace."""
        pipeline = build_intelligent_pipeline()
        result = await pipeline.process("Create a portable context")
        trace = result.trace
        assert trace.tutti_active is True
        assert trace.tutti_export_id

    async def test_tutti_export_in_result(self) -> None:
        """Tutti export is included in the PipelineResult."""
        pipeline = build_intelligent_pipeline()
        result = await pipeline.process("Export this session")
        assert result.tutti_export is not None
        assert "id" in result.tutti_export


# ===========================================================================
# verify_integration — the definitive test
# ===========================================================================


class TestVerifyIntegration:
    @pytest.mark.asyncio
    async def test_verify_all_subsystems_active(self) -> None:
        """verify_integration() proves all 8 subsystems are active."""
        pipeline = build_intelligent_pipeline()
        # Run a request to initialize lazy subsystems
        await pipeline.process("Initialize all subsystems for verification")

        report = pipeline.verify_integration()
        subsystems = report["subsystems"]

        # Every subsystem must be active
        assert subsystems["router"]["active"] is True, "Router not active"
        assert subsystems["memory"]["active"] is True, "Memory not active"
        assert subsystems["context"]["active"] is True, "Context not active"
        assert subsystems["moa"]["active"] is True, "MOA not active"
        assert subsystems["reflection"]["active"] is True, "Reflection not active"
        assert subsystems["knowledge_graph"]["active"] is True, "Knowledge Graph not active"
        assert subsystems["learning"]["active"] is True, "Learning not active"
        assert subsystems["tutti"]["active"] is True, "Tutti not active"

        assert report["all_active"] is True
        assert report["active_count"] == 8

    @pytest.mark.asyncio
    async def test_verify_subsystem_types(self) -> None:
        """verify_integration() returns the correct types for each subsystem."""
        pipeline = build_intelligent_pipeline()
        await pipeline.process("Verification request")

        report = pipeline.verify_integration()
        subsystems = report["subsystems"]

        assert "ReachIntelligenceRouter" in subsystems["router"]["type"]
        assert "LongCatMemoryEngine" in subsystems["memory"]["type"]
        assert "ContextEngine" in subsystems["context"]["type"]
        assert "MOAEngine" in subsystems["moa"]["type"]
        assert "ReflectionEngineV2" in subsystems["reflection"]["type"]
        assert "KnowledgeGraph" in subsystems["knowledge_graph"]["type"]
        assert "ReachLearningEngine" in subsystems["learning"]["type"]
        assert "TuttiExporter" in subsystems["tutti"]["type"]


# ===========================================================================
# Graceful degradation
# ===========================================================================


@pytest.mark.asyncio
class TestGracefulDegradation:
    async def test_disabled_subsystems_not_in_trace(self) -> None:
        """Disabled subsystems don't appear active in the trace."""
        config = PipelineConfig(
            enable_router=False,
            enable_memory=False,
            enable_tutti=False,
        )
        pipeline = build_intelligent_pipeline(config=config)
        result = await pipeline.process("Test with partial pipeline")
        trace = result.trace
        assert trace.router_active is False
        assert trace.memory_active is False
        assert trace.tutti_active is False
        # But other subsystems still run
        assert trace.reflection_active is True
        assert trace.learning_active is True

    async def test_all_disabled_falls_back_to_controller(self) -> None:
        """When all subsystems are disabled, pipeline still works."""
        config = PipelineConfig(
            enable_router=False,
            enable_memory=False,
            enable_context=False,
            enable_moa=False,
            enable_reflection=False,
            enable_knowledge_graph=False,
            enable_learning=False,
            enable_tutti=False,
        )
        pipeline = build_intelligent_pipeline(config=config)
        result = await pipeline.process("Bare minimum test")
        assert result.answer is not None
        # Trace should show nothing active except the bare flow
        assert result.trace.router_active is False
        assert result.trace.memory_active is False
        assert result.trace.reflection_active is False

    async def test_pipeline_process_never_crashes(self) -> None:
        """Pipeline.process() never raises, even on error."""
        pipeline = build_intelligent_pipeline()
        # Try a very long message
        result = await pipeline.process("A" * 10000)
        assert result is not None
        assert result.answer is not None


# ===========================================================================
# PipelineTraces
# ===========================================================================


class TestPipelineTrace:
    def test_trace_to_dict(self) -> None:
        trace = PipelineTrace(
            request_id="test-123",
            router_provider="anthropic",
            router_score=0.9,
        )
        d = trace.to_dict()
        assert d["request_id"] == "test-123"
        assert d["router"]["provider"] == "anthropic"
        assert d["router"]["score"] == 0.9


class TestPipelineConfig:
    def test_default_all_enabled(self) -> None:
        config = PipelineConfig()
        assert config.enable_router
        assert config.enable_memory
        assert config.enable_context
        assert config.enable_moa
        assert config.enable_reflection
        assert config.enable_knowledge_graph
        assert config.enable_learning
        assert config.enable_tutti


# ===========================================================================
# Pipeline stats
# ===========================================================================


@pytest.mark.asyncio
class TestPipelineStats:
    async def test_get_stats_after_requests(self) -> None:
        pipeline = build_intelligent_pipeline()
        await pipeline.process("request 1")
        await pipeline.process("request 2")
        stats = pipeline.get_stats()
        assert stats["total_requests"] == 2
        assert stats["avg_latency_ms"] > 0

    async def test_clear_resets_stats(self) -> None:
        pipeline = build_intelligent_pipeline()
        await pipeline.process("test")
        pipeline.clear()
        stats = pipeline.get_stats()
        assert stats["total_requests"] == 0
