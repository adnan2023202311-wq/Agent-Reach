"""Tests for M7.5-M7.8: Reflection V2, Skill Ecosystem, Prompt Intelligence, Knowledge Graph."""
from __future__ import annotations

import pytest
import time

from reflection.v2_engine import ReflectionEngineV2, V2ReflectionReport, ReflectionMemory
from evaluation.engine import EvaluationCriteria, EvaluationEngine, EvaluationReport, EvaluationResult
from reflection.engine import ReflectionInsight

from skills.ecosystem import (
    SkillComposition,
    SkillDependency,
    SkillEcosystem,
    SkillMetadata,
)
from skills.engine import Skill

from prompts.intelligence import PromptIntelligence, PromptRankingMethod, PromptRanking
from prompts.library import PromptTemplate

from knowledge.graph import KnowledgeGraph, KnowledgeNode, KnowledgeEdge, NodeType, EdgeType


# ===========================================================================
# M7.5 Reflection Engine V2
# ===========================================================================

class TestReflectionEngineV2:
    def test_reflect_scoring(self) -> None:
        engine = ReflectionEngineV2()
        report = EvaluationReport(results=[
            EvaluationResult(criterion_name="accuracy", score=0.9, passed=True, weight=1.0),
            EvaluationResult(criterion_name="completeness", score=0.8, passed=True, weight=1.0),
        ])
        result = engine.reflect(report)
        assert result.reflection_score == pytest.approx(85.0)
        assert not result.should_auto_retry

    def test_reflect_detects_errors(self) -> None:
        engine = ReflectionEngineV2()
        report = EvaluationReport(results=[
            EvaluationResult(criterion_name="accuracy", score=0.2, passed=False, weight=1.0),
        ])
        result = engine.reflect(report)
        assert result.error_detected
        assert result.should_auto_retry

    def test_reflect_suggests_improvements(self) -> None:
        engine = ReflectionEngineV2()
        report = EvaluationReport(results=[
            EvaluationResult(criterion_name="accuracy", score=0.3, passed=False, weight=1.0),
        ])
        result = engine.reflect(report)
        assert len(result.improvement_suggestions) > 0

    def test_critique_empty_output(self) -> None:
        engine = ReflectionEngineV2()
        result = engine.critique("", expected="something")
        assert result.error_detected
        assert any("empty" in i.message.lower() for i in result.insights)

    def test_critique_differs_from_expected(self) -> None:
        engine = ReflectionEngineV2()
        result = engine.critique("short", expected="a very long expected output that is much longer")
        assert result.reflection_score < 100

    def test_critique_short_output(self) -> None:
        engine = ReflectionEngineV2()
        result = engine.critique("hi")
        assert len(result.insights) > 0

    def test_record_improvement(self) -> None:
        engine = ReflectionEngineV2()
        insight = ReflectionInsight(category="accuracy", severity="high", message="test")
        engine.record_improvement("test context", insight, "fixed formatting")
        effective = engine.get_effective_improvements()
        assert len(effective) == 1

    def test_record_ineffective_improvement(self) -> None:
        engine = ReflectionEngineV2()
        insight = ReflectionInsight(category="accuracy", severity="high", message="test")
        engine.record_improvement("context", insight, "bad fix", was_effective=False)
        effective = engine.get_effective_improvements()
        assert len(effective) == 0

    def test_retry_strategies(self) -> None:
        engine = ReflectionEngineV2()
        # Very low score -> different_provider
        report_low = EvaluationReport(results=[
            EvaluationResult(criterion_name="x", score=0.1, passed=False, weight=1.0),
        ])
        result_low = engine.reflect(report_low)
        assert result_low.retry_strategy == "different_provider"

        # Medium score -> revised_prompt
        report_med = EvaluationReport(results=[
            EvaluationResult(criterion_name="x", score=0.4, passed=False, weight=1.0),
        ])
        result_med = engine.reflect(report_med)
        assert result_med.retry_strategy == "revised_prompt"

    def test_get_stats(self) -> None:
        engine = ReflectionEngineV2()
        report = EvaluationReport(results=[
            EvaluationResult(criterion_name="x", score=0.5, passed=True, weight=1.0),
        ])
        engine.reflect(report)
        stats = engine.get_stats()
        assert stats["total_reflections"] == 1

    def test_clear(self) -> None:
        engine = ReflectionEngineV2()
        report = EvaluationReport(results=[
            EvaluationResult(criterion_name="x", score=0.5, passed=True, weight=1.0),
        ])
        engine.reflect(report)
        engine.clear()
        stats = engine.get_stats()
        assert stats["total_reflections"] == 0


# ===========================================================================
# M7.6 Skill Ecosystem
# ===========================================================================

class TestSkillEcosystem:
    @pytest.mark.asyncio
    async def test_register_with_metadata(self) -> None:
        async def dummy_exec(**kwargs): return "done"
        ecosystem = SkillEcosystem()
        skill = Skill(id="s1", name="test_skill", description="A test skill", executor=dummy_exec)
        meta = SkillMetadata(author="test_author", category="test", tags=["tag1"])
        ecosystem.register(skill, metadata=meta)
        assert ecosystem.registry.get("s1") is not None

    @pytest.mark.asyncio
    async def test_discover_by_category(self) -> None:
        async def dummy_exec(**kwargs): return "done"
        ecosystem = SkillEcosystem()
        s1 = Skill(id="s1", name="skill_a", executor=dummy_exec)
        s2 = Skill(id="s2", name="skill_b", executor=dummy_exec)
        ecosystem.register(s1, metadata=SkillMetadata(category="cat_a"))
        ecosystem.register(s2, metadata=SkillMetadata(category="cat_b"))
        results = ecosystem.discover(category="cat_a")
        assert len(results) == 1
        assert results[0].id == "s1"

    @pytest.mark.asyncio
    async def test_search(self) -> None:
        async def dummy_exec(**kwargs): return "done"
        ecosystem = SkillEcosystem()
        s1 = Skill(id="s1", name="python_skill", executor=dummy_exec)
        ecosystem.register(s1, metadata=SkillMetadata(tags=["python"]))
        results = ecosystem.search("python")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_dependencies(self) -> None:
        async def dummy_exec(**kwargs): return "done"
        ecosystem = SkillEcosystem()
        s1 = Skill(id="s1", name="base", executor=dummy_exec)
        s2 = Skill(id="s2", name="derived", executor=dummy_exec)
        ecosystem.register(s1)
        ecosystem.register(s2, dependencies=[SkillDependency(skill_id="s1")])
        deps = ecosystem.get_dependencies("s2")
        assert len(deps) == 1
        assert deps[0].skill_id == "s1"

    @pytest.mark.asyncio
    async def test_validate_dependencies(self) -> None:
        async def dummy_exec(**kwargs): return "done"
        ecosystem = SkillEcosystem()
        s2 = Skill(id="s2", name="derived", executor=dummy_exec)
        ecosystem.register(s2, dependencies=[SkillDependency(skill_id="missing")])
        missing = ecosystem.validate_dependencies("s2")
        assert "missing" in missing

    @pytest.mark.asyncio
    async def test_resolve_dependencies(self) -> None:
        async def dummy_exec(**kwargs): return "done"
        ecosystem = SkillEcosystem()
        s1 = Skill(id="s1", name="base", executor=dummy_exec)
        s2 = Skill(id="s2", name="middle", executor=dummy_exec)
        s3 = Skill(id="s3", name="top", executor=dummy_exec)
        ecosystem.register(s1)
        ecosystem.register(s2, dependencies=[SkillDependency(skill_id="s1")])
        ecosystem.register(s3, dependencies=[SkillDependency(skill_id="s2")])
        resolved = ecosystem.resolve_dependencies("s3")
        assert len(resolved) == 3
        assert resolved[0].id == "s1"  # dependencies first

    @pytest.mark.asyncio
    async def test_versioning(self) -> None:
        async def dummy_exec(**kwargs): return "done"
        ecosystem = SkillEcosystem()
        s1 = Skill(id="v1", name="my_skill", version="1.0.0", executor=dummy_exec)
        s2 = Skill(id="v2", name="my_skill", version="2.0.0", executor=dummy_exec)
        ecosystem.register(s1)
        ecosystem.register(s2)
        versions = ecosystem.get_versions("my_skill")
        assert len(versions) == 2
        latest = ecosystem.get_latest_version("my_skill")
        assert latest.id == "v2"

    @pytest.mark.asyncio
    async def test_composition(self) -> None:
        async def dummy_exec(**kwargs): return "done"
        ecosystem = SkillEcosystem()
        s1 = Skill(id="s1", name="step1", executor=dummy_exec)
        s2 = Skill(id="s2", name="step2", executor=dummy_exec)
        ecosystem.register(s1)
        ecosystem.register(s2)
        comp = ecosystem.compose("pipeline", ["s1", "s2"], "A test pipeline")
        assert comp.skills == ["s1", "s2"]

        results = await ecosystem.execute_composition("pipeline", {"input": "test"})
        assert len(results) == 2
        assert results[0].success
        assert results[1].success

    @pytest.mark.asyncio
    async def test_test_skill(self) -> None:
        async def echo(**kwargs): return kwargs.get("msg", "")
        ecosystem = SkillEcosystem()
        skill = Skill(id="echo", name="echo", executor=echo)
        ecosystem.register(skill)
        result = await ecosystem.test_skill("echo", {"msg": "hello"}, expected_output="hello")
        assert result["passed"]

    @pytest.mark.asyncio
    async def test_export_manifest(self) -> None:
        async def dummy_exec(**kwargs): return "done"
        ecosystem = SkillEcosystem()
        skill = Skill(id="s1", name="exported", description="test", executor=dummy_exec)
        meta = SkillMetadata(author="me", category="tools", tags=["export"])
        ecosystem.register(skill, metadata=meta)
        manifest = ecosystem.export_manifest("s1")
        assert manifest is not None
        assert manifest["author"] == "me"

    @pytest.mark.asyncio
    async def test_get_stats(self) -> None:
        async def dummy_exec(**kwargs): return "done"
        ecosystem = SkillEcosystem()
        skill = Skill(id="s1", name="stat_skill", executor=dummy_exec)
        ecosystem.register(skill, metadata=SkillMetadata(category="test"))
        stats = ecosystem.get_stats()
        assert stats["total_skills"] == 1


# ===========================================================================
# M7.7 Prompt Intelligence
# ===========================================================================

class TestPromptIntelligence:
    def test_build_prompt_default(self) -> None:
        pi = PromptIntelligence()
        prompt = pi.build_prompt("Summarize this article")
        assert "Summarize" in prompt

    def test_build_prompt_with_context(self) -> None:
        pi = PromptIntelligence()
        prompt = pi.build_prompt("Answer", {"topic": "AI", "style": "concise"})
        assert "topic" in prompt
        assert "AI" in prompt

    def test_build_prompt_styles(self) -> None:
        pi = PromptIntelligence()
        concise = pi.build_prompt("Task", style="concise")
        detailed = pi.build_prompt("Task", style="detailed")
        assert len(detailed) > len(concise)

    def test_select_best_prompt(self) -> None:
        pi = PromptIntelligence()
        pi.library.register("summarize", "Please summarize: {{ text }}", tags=["summarization"])
        pi.library.register("code_review", "Review this code: {{ code }}", tags=["coding"])
        result = pi.select_best_prompt("summarization")
        assert result is not None

    def test_rank_prompts_by_score(self) -> None:
        pi = PromptIntelligence()
        pi.library.register("p1", "template 1")
        pi.library.register("p2", "template 2")
        pi.record_usage("p1", output_quality=0.9)
        pi.record_usage("p2", output_quality=0.5)
        prompts = pi.library.list_prompts()
        ranked = pi.rank_prompts(prompts, method=PromptRankingMethod.SCORE)
        assert len(ranked) == 2
        assert ranked[0].score >= ranked[1].score

    def test_rank_prompts_by_usage(self) -> None:
        pi = PromptIntelligence()
        pi.library.register("p1", "template 1")
        pi.library.register("p2", "template 2")
        for _ in range(3):
            pi.record_usage("p2", output_quality=0.5)
        pi.record_usage("p1", output_quality=0.5)
        prompts = pi.library.list_prompts()
        ranked = pi.rank_prompts(prompts, method=PromptRankingMethod.USAGE)
        assert ranked[0].prompt.name == "p2"

    def test_suggest_optimizations(self) -> None:
        pi = PromptIntelligence()
        pi.library.register("short", "hi")
        suggestions = pi.suggest_optimizations("short")
        assert any("short" in s.lower() for s in suggestions)

    def test_suggest_optimizations_no_description(self) -> None:
        pi = PromptIntelligence()
        pi.library.register("no_desc", "A reasonable template with enough content to be usable")
        suggestions = pi.suggest_optimizations("no_desc")
        assert any("description" in s.lower() for s in suggestions)

    def test_record_usage_and_learning(self) -> None:
        pi = PromptIntelligence()
        pi.library.register("learn", "Learn {{ topic }}")
        pi.record_usage("learn", {"topic": "math"}, output_quality=0.8, latency_ms=500.0, provider="openai")
        stats = pi.get_learning_stats("learn")
        assert stats["total_uses"] == 1
        assert stats["avg_quality"] == 0.8

    def test_get_stats(self) -> None:
        pi = PromptIntelligence()
        pi.library.register("test", "test template", tags=["test"])
        pi.record_usage("test", output_quality=0.7)
        stats = pi.get_stats()
        assert stats["total"] == 1

    def test_clear(self) -> None:
        pi = PromptIntelligence()
        pi.library.register("test", "test")
        pi.record_usage("test")
        pi.clear()
        stats = pi.get_stats()
        assert stats["total"] == 0


# ===========================================================================
# M7.8 Knowledge Graph
# ===========================================================================

class TestKnowledgeGraph:
    def test_add_and_get_node(self) -> None:
        kg = KnowledgeGraph()
        nid = kg.add_node(NodeType.PROJECT, "Project Alpha", "A test project")
        node = kg.get_node(nid)
        assert node is not None
        assert node.label == "Project Alpha"
        assert node.node_type == NodeType.PROJECT

    def test_find_nodes_by_type(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(NodeType.AGENT, "Agent A")
        kg.add_node(NodeType.SKILL, "Skill B")
        agents = kg.find_nodes(node_type=NodeType.AGENT)
        assert len(agents) == 1
        assert agents[0].label == "Agent A"

    def test_find_nodes_by_label(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(NodeType.FILE, "main.py")
        kg.add_node(NodeType.FILE, "test.py")
        results = kg.find_nodes(label_contains="main")
        assert len(results) == 1

    def test_add_edge(self) -> None:
        kg = KnowledgeGraph()
        n1 = kg.add_node(NodeType.AGENT, "Agent 1")
        n2 = kg.add_node(NodeType.SKILL, "Skill 1")
        eid = kg.add_edge(n1, n2, EdgeType.USES)
        assert eid is not None
        edge = kg.get_edge(eid)
        assert edge is not None
        assert edge.edge_type == EdgeType.USES

    def test_add_edge_invalid_nodes(self) -> None:
        kg = KnowledgeGraph()
        eid = kg.add_edge("nonexistent1", "nonexistent2", EdgeType.RELATED_TO)
        assert eid is None

    def test_remove_edge(self) -> None:
        kg = KnowledgeGraph()
        n1 = kg.add_node(NodeType.AGENT, "A")
        n2 = kg.add_node(NodeType.SKILL, "S")
        eid = kg.add_edge(n1, n2, EdgeType.USES)
        assert kg.remove_edge(eid)
        assert kg.get_edge(eid) is None

    def test_remove_node_cascades(self) -> None:
        kg = KnowledgeGraph()
        n1 = kg.add_node(NodeType.AGENT, "A")
        n2 = kg.add_node(NodeType.SKILL, "S")
        kg.add_edge(n1, n2, EdgeType.USES)
        kg.remove_node(n1)
        assert kg.get_node(n1) is None

    def test_get_neighbors(self) -> None:
        kg = KnowledgeGraph()
        n1 = kg.add_node(NodeType.PROJECT, "P")
        n2 = kg.add_node(NodeType.AGENT, "A")
        n3 = kg.add_node(NodeType.SKILL, "S")
        kg.add_edge(n1, n2, EdgeType.USES)
        kg.add_edge(n1, n3, EdgeType.REQUIRES)
        neighbors = kg.get_neighbors(n1, direction="outgoing")
        assert len(neighbors) == 2

    def test_get_neighbors_filtered(self) -> None:
        kg = KnowledgeGraph()
        n1 = kg.add_node(NodeType.PROJECT, "P")
        n2 = kg.add_node(NodeType.AGENT, "A")
        n3 = kg.add_node(NodeType.SKILL, "S")
        kg.add_edge(n1, n2, EdgeType.USES)
        kg.add_edge(n1, n3, EdgeType.REQUIRES)
        neighbors = kg.get_neighbors(n1, direction="outgoing", edge_type=EdgeType.USES)
        assert len(neighbors) == 1

    def test_traverse(self) -> None:
        kg = KnowledgeGraph()
        n1 = kg.add_node(NodeType.PROJECT, "P")
        n2 = kg.add_node(NodeType.AGENT, "A")
        n3 = kg.add_node(NodeType.SKILL, "S")
        n4 = kg.add_node(NodeType.MEMORY, "M")
        kg.add_edge(n1, n2, EdgeType.USES)
        kg.add_edge(n2, n3, EdgeType.REQUIRES)
        kg.add_edge(n3, n4, EdgeType.DEPENDS_ON)
        results = kg.traverse(n1, max_depth=3)
        assert len(results) == 3

    def test_find_path(self) -> None:
        kg = KnowledgeGraph()
        n1 = kg.add_node(NodeType.PROJECT, "Start")
        n2 = kg.add_node(NodeType.AGENT, "Middle")
        n3 = kg.add_node(NodeType.SKILL, "End")
        kg.add_edge(n1, n2, EdgeType.USES)
        kg.add_edge(n2, n3, EdgeType.REQUIRES)
        path = kg.find_path(n1, n3)
        assert path is not None
        assert path == [n1, n2, n3]

    def test_find_path_no_connection(self) -> None:
        kg = KnowledgeGraph()
        n1 = kg.add_node(NodeType.PROJECT, "A")
        n2 = kg.add_node(NodeType.SKILL, "B")
        path = kg.find_path(n1, n2)
        assert path is None

    def test_get_subgraph(self) -> None:
        kg = KnowledgeGraph()
        n1 = kg.add_node(NodeType.PROJECT, "P1")
        n2 = kg.add_node(NodeType.AGENT, "A1")
        kg.add_edge(n1, n2, EdgeType.USES)
        sub = kg.get_subgraph([n1, n2])
        assert len(sub["nodes"]) == 2
        assert len(sub["edges"]) == 1

    def test_get_by_type(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(NodeType.AGENT, "A1")
        kg.add_node(NodeType.AGENT, "A2")
        kg.add_node(NodeType.SKILL, "S1")
        agents = kg.get_by_type(NodeType.AGENT)
        assert len(agents) == 2

    def test_get_related_by_type(self) -> None:
        kg = KnowledgeGraph()
        n1 = kg.add_node(NodeType.PROJECT, "P")
        n2 = kg.add_node(NodeType.AGENT, "A")
        n3 = kg.add_node(NodeType.SKILL, "S")
        kg.add_edge(n1, n2, EdgeType.USES)
        kg.add_edge(n2, n3, EdgeType.REQUIRES)
        related = kg.get_related_by_type(n1, NodeType.SKILL, max_depth=3)
        assert len(related) == 1

    def test_get_stats(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(NodeType.AGENT, "A")
        kg.add_node(NodeType.SKILL, "S")
        kg.add_edge(
            kg.find_nodes(node_type=NodeType.AGENT)[0].id,
            kg.find_nodes(node_type=NodeType.SKILL)[0].id,
            EdgeType.USES,
        )
        stats = kg.get_stats()
        assert stats["total_nodes"] == 2
        assert stats["total_edges"] == 1

    def test_clear(self) -> None:
        kg = KnowledgeGraph()
        kg.add_node(NodeType.AGENT, "A")
        kg.add_edge("a", "b", EdgeType.RELATED_TO)
        kg.clear()
        assert kg.get_stats()["total_nodes"] == 0
        assert kg.get_stats()["total_edges"] == 0

    def test_all_node_types(self) -> None:
        kg = KnowledgeGraph()
        for nt in NodeType:
            kg.add_node(nt, f"Node of {nt.value}")
        stats = kg.get_stats()
        assert stats["total_nodes"] == len(NodeType)

    def test_all_edge_types(self) -> None:
        kg = KnowledgeGraph()
        n1 = kg.add_node(NodeType.PROJECT, "P")
        for i, et in enumerate(EdgeType):
            target = kg.add_node(NodeType.AGENT, f"Agent_{i}")
            kg.add_edge(n1, target, et)
        stats = kg.get_stats()
        assert stats["total_edges"] == len(EdgeType)
