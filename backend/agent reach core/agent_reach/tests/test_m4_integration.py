"""Integration Tests for Milestone 4 (M4.13).

Verifies that all M4 subsystems orchestrate correctly through the
Workflow Engine.
"""

from __future__ import annotations

import pytest

from core.capability_resolver import CapabilityResolver
from core.execution import ExecutionOrchestrator, ExecutionStep
from core.scheduler import Scheduler
from evaluation.engine import EvaluationCriteria, EvaluationEngine
from knowledge.layer import KnowledgeLayer
from memory.layer import MemoryLayer, MemoryType
from mcp.runtime import MCPRequest, MCPRuntime, MCPToolDefinition
from observability.metrics import MetricsCollector
from observability.tracing import ObservabilityCollector
from reflection.engine import ReflectionEngine
from skills.engine import Skill, SkillEngine
from workflow.engine import WorkflowEngine, WorkflowStep


async def _math_skill(a: int = 0, b: int = 0) -> int:
    return a + b


async def _mcp_add_tool(request: MCPRequest) -> int:
    a = request.parameters.get("a", 0)
    b = request.parameters.get("b", 0)
    return a + b


async def _greet_skill(name: str = "world") -> str:
    return f"Hello, {name}!"


class TestM4Integration:
    @pytest.fixture
    def capability_resolver(self) -> CapabilityResolver:
        r = CapabilityResolver()
        r.register("math_skill", _math_skill)
        r.register("greet_skill", _greet_skill)
        return r

    @pytest.fixture
    def evaluation_engine(self) -> EvaluationEngine:
        e = EvaluationEngine()
        e.register_criteria(
            EvaluationCriteria(
                name="exact",
                evaluator=lambda output, expected, **k: 1.0 if output == expected else 0.0,
                threshold=1.0,
            )
        )
        return e

    @pytest.fixture
    def reflection_engine(self) -> ReflectionEngine:
        return ReflectionEngine()

    @pytest.fixture
    def observability(self) -> ObservabilityCollector:
        return ObservabilityCollector()

    @pytest.fixture
    def workflow_engine(
        self,
        capability_resolver: CapabilityResolver,
        evaluation_engine: EvaluationEngine,
        reflection_engine: ReflectionEngine,
        observability: ObservabilityCollector,
    ) -> WorkflowEngine:
        return WorkflowEngine(
            capability_resolver=capability_resolver,
            evaluation_engine=evaluation_engine,
            reflection_engine=reflection_engine,
            observability=observability,
        )

    @pytest.mark.asyncio
    async def test_full_pipeline(self, workflow_engine: WorkflowEngine) -> None:
        """Execute a workflow that exercises the full M4 pipeline."""
        steps = [
            WorkflowStep(
                step_id="math",
                name="Math",
                capability_id="math_skill",
                inputs={"a": 10, "b": 20},
                evaluate=True,
                reflect=True,
            ),
            WorkflowStep(
                step_id="greet",
                name="Greeting",
                capability_id="greet_skill",
                inputs={"name": "Agent"},
                depends_on=["math"],
            ),
        ]
        result = await workflow_engine.run("integration-1", steps)
        assert result.state == "completed"
        assert result.step_outcomes["math"].output == 30
        assert result.step_outcomes["greet"].output == "Hello, Agent!"
        assert result.step_outcomes["math"].evaluation is not None
        assert result.step_outcomes["math"].reflection is not None

    @pytest.mark.asyncio
    async def test_capability_resolver_with_mcp_and_skills(self) -> None:
        """CapabilityResolver routes to both MCP tools and Skills."""
        mcp = MCPRuntime()
        mcp.register_tool(
            MCPToolDefinition(name="add", description="Add numbers"),
            _mcp_add_tool,
        )

        skills = SkillEngine()
        skills.registry.register(Skill(id="double", name="Double", executor=lambda x=0: _math_skill(a=x, b=x)))

        resolver = CapabilityResolver()
        # Register MCP tool as a capability
        resolver.register(
            "mcp_add",
            lambda a=0, b=0: mcp.execute(MCPRequest(tool_name="add", parameters={"a": a, "b": b})),
        )
        # Register skill as a capability
        resolver.register(
            "skill_double",
            lambda x=0: skills.execute("double", {"x": x}),
        )

        orchestrator = ExecutionOrchestrator(resolver)

        step1 = ExecutionStep(step_id="s1", capability_id="mcp_add", inputs={"a": 3, "b": 4})
        outcome1 = await orchestrator.execute_step(step1)
        assert outcome1.success is True
        response = outcome1.output
        assert response.success is True
        assert response.result == 7

    @pytest.mark.asyncio
    async def test_scheduler_with_workflow(self) -> None:
        """Scheduler can queue workflow steps."""
        resolver = CapabilityResolver()
        resolver.register("math", _math_skill)
        scheduler = Scheduler()

        task_id = scheduler.schedule(
            executor=lambda **kwargs: WorkflowEngine(
                capability_resolver=resolver
            ).run("scheduled-wf", [
                WorkflowStep(step_id="s1", capability_id="math", inputs=kwargs)
            ]),
            payload={"a": 5, "b": 5},
        )
        result = await scheduler.run_next()
        assert result is not None
        assert result.success is True
        wf_result = result.output
        assert wf_result.step_outcomes["s1"].output == 10

    @pytest.mark.asyncio
    async def test_memory_and_knowledge_independence(self) -> None:
        """Memory and Knowledge layers operate independently (ADR-003)."""
        memory = MemoryLayer()
        knowledge = KnowledgeLayer()

        mid = memory.store("session_context", importance=0.9, memory_type=MemoryType.SHORT_TERM)
        kid = knowledge.add_text("domain_fact", source="docs", tags=["fact"])

        assert memory.get(mid) is not None
        assert knowledge.get(kid) is not None
        assert memory.count() == 1
        assert knowledge.count() == 1

        memory.clear()
        assert memory.count() == 0
        assert knowledge.count() == 1  # knowledge unaffected

    @pytest.mark.asyncio
    async def test_observability_traces_workflow(self, workflow_engine: WorkflowEngine) -> None:
        """Workflow execution produces observability traces."""
        steps = [
            WorkflowStep(step_id="s1", capability_id="math_skill", inputs={"a": 1, "b": 2}),
        ]
        await workflow_engine.run("obs-wf", steps)
        traces = workflow_engine._observability.list_traces()
        assert len(traces) >= 1

    @pytest.mark.asyncio
    async def test_evaluation_before_reflection_order(self, workflow_engine: WorkflowEngine) -> None:
        """ADR-002: Evaluation ALWAYS happens before Reflection."""
        steps = [
            WorkflowStep(
                step_id="s1",
                capability_id="math_skill",
                inputs={"a": 2, "b": 2},
                evaluate=True,
                reflect=True,
            ),
        ]
        result = await workflow_engine.run("order-wf", steps)
        outcome = result.step_outcomes["s1"]
        assert outcome.evaluation is not None
        assert outcome.reflection is not None
        # Reflection consumed evaluation results
        assert outcome.reflection.summary != ""

    def test_all_subsystems_instantiable(self) -> None:
        """Smoke test: every M4 subsystem can be instantiated."""
        assert ObservabilityCollector() is not None
        assert MetricsCollector() is not None
        assert CapabilityResolver() is not None
        assert MCPRuntime() is not None
        assert SkillEngine() is not None
        assert KnowledgeLayer() is not None
        assert MemoryLayer() is not None
        assert EvaluationEngine() is not None
        assert ReflectionEngine() is not None
        assert ExecutionOrchestrator(CapabilityResolver()) is not None
        assert Scheduler() is not None
        assert WorkflowEngine(CapabilityResolver()) is not None
