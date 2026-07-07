"""Integration tests for the M5 Workflow & Orchestration Layer (M5.9).

These tests exercise the M5 subsystems together — Registry, Engine,
Persistence, Validation, and Monitoring — the way a real workflow
author would use them.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.dispatcher import AgentDispatcher
from core.tool_executor import ToolExecutor
from domain.models import AgentType, RetryPolicy, SubTask
from workflows.engine import WorkflowEngine
from workflows.models import (
    Condition,
    ConditionOp,
    StepType,
    Workflow,
    WorkflowResult,
    WorkflowState,
    WorkflowStep,
)
from workflows.monitoring import WorkflowMonitor
from workflows.orchestration import AgentOrchestrator, ToolOrchestrator
from workflows.persistence import (
    load_workflow,
    save_result,
    save_workflow,
)
from workflows.registry import WorkflowRegistry
from workflows.validation import (
    ValidationResult,
    WorkflowValidator,
    validate_structure,
)


# ---------------------------------------------------------------------------
# Test fixtures / fakes
# ---------------------------------------------------------------------------


class EchoAgent:
    """Fake Agent implementation for integration tests."""

    def __init__(self, agent_type: AgentType) -> None:
        self._type = agent_type

    @property
    def agent_type(self) -> AgentType:
        return self._type

    async def execute(self, subtask: SubTask) -> dict[str, object]:
        return {
            "text": f"echo:{subtask.description}",
            "input": dict(subtask.input_data),
        }


def _fast_retry() -> RetryPolicy:
    return RetryPolicy(max_attempts=2, backoff_seconds=0.0)


@pytest.fixture
def dispatcher() -> AgentDispatcher:
    return AgentDispatcher(
        agents={
            AgentType.RESEARCH: EchoAgent(AgentType.RESEARCH),
            AgentType.CODING: EchoAgent(AgentType.CODING),
        },
        retry_policy=_fast_retry(),
    )


@pytest.fixture
def tool_orchestrator() -> ToolOrchestrator:
    orch = ToolOrchestrator()

    async def add(a: int = 0, b: int = 0) -> int:
        return a + b

    async def shout(text: str = "") -> str:
        return text.upper()

    async def boom() -> None:
        raise RuntimeError("tool boom")

    orch.executor.register_tool("add", add)
    orch.executor.register_tool("shout", shout)
    orch.executor.register_tool("boom", boom)
    return orch


@pytest.fixture
def agent_orchestrator(dispatcher: AgentDispatcher) -> AgentOrchestrator:
    return AgentOrchestrator(dispatcher=dispatcher)


@pytest.fixture
def engine(
    agent_orchestrator: AgentOrchestrator,
    tool_orchestrator: ToolOrchestrator,
) -> WorkflowEngine:
    return WorkflowEngine(
        agent_orchestrator=agent_orchestrator,
        tool_orchestrator=tool_orchestrator,
    )


@pytest.fixture
def monitor() -> WorkflowMonitor:
    return WorkflowMonitor()


# ---------------------------------------------------------------------------
# Agent orchestration through the engine
# ---------------------------------------------------------------------------


class TestAgentOrchestrationIntegration:
    @pytest.mark.asyncio
    async def test_sequential_agents(
        self,
        engine: WorkflowEngine,
        monitor: WorkflowMonitor,
    ) -> None:
        wf = Workflow(
            name="seq-agents",
            steps=[
                WorkflowStep(
                    step_id="research",
                    type=StepType.AGENT,
                    target="research",
                    inputs={"q": "what is AI?"},
                    output_keys=["text"],
                ),
                WorkflowStep(
                    step_id="coding",
                    type=StepType.AGENT,
                    target="coding",
                    inputs={"instruction": "write a haiku"},
                    output_keys=["text"],
                    depends_on=["research"],
                ),
            ],
            outputs={
                "research_text": "outputs.research.text",
                "coding_text": "outputs.coding.text",
            },
        )
        result = await engine.run(wf)
        monitor.record(result)
        assert result.state == WorkflowState.COMPLETED
        # The EchoAgent prepends "echo:" to the step description
        # (which the engine sets to the step's name). Inputs flow
        # through untouched and are visible in the agent output.
        assert "echo:research" == result.outputs["research_text"]
        assert "echo:coding" == result.outputs["coding_text"]
        assert result.history[0].output["input"]["q"] == "what is AI?"
        assert result.history[1].output["input"]["instruction"] == "write a haiku"
        stats = monitor.get_stats()
        assert stats.completed == 1
        assert stats.failed == 0

    @pytest.mark.asyncio
    async def test_conditional_agent(
        self,
        engine: WorkflowEngine,
    ) -> None:
        wf = Workflow(
            name="conditional-agent",
            variables={"go": False},
            steps=[
                WorkflowStep(
                    step_id="research",
                    type=StepType.AGENT,
                    target="research",
                    inputs={"q": "what?"},
                    condition=Condition("go", ConditionOp.TRUTHY),
                    output_keys=["text"],
                )
            ],
            outputs={"text": "outputs.research.text"},
        )
        result = await engine.run(wf)
        assert result.state == WorkflowState.COMPLETED
        assert result.outputs["text"] is None
        assert result.history[0].skipped is True


# ---------------------------------------------------------------------------
# Tool orchestration through the engine
# ---------------------------------------------------------------------------


class TestToolOrchestrationIntegration:
    @pytest.mark.asyncio
    async def test_tool_with_parameter_passing(
        self,
        engine: WorkflowEngine,
    ) -> None:
        wf = Workflow(
            name="tool-chain",
            variables={"x": 5},
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": "{{ variables.x }}", "b": 3},
                    output_keys=["sum"],
                ),
                WorkflowStep(
                    step_id="s2",
                    type=StepType.TOOL,
                    target="shout",
                    inputs={"text": "sum={{ outputs.s1.sum }}"},
                    output_keys=["text"],
                    depends_on=["s1"],
                ),
            ],
            outputs={
                "sum": "outputs.s1.sum",
                "loud": "outputs.s2.text",
            },
        )
        result = await engine.run(wf)
        assert result.state == WorkflowState.COMPLETED
        assert result.outputs["sum"] == 8
        assert result.outputs["loud"] == "SUM=8"

    @pytest.mark.asyncio
    async def test_tool_failure_with_default_retry(
        self,
        engine: WorkflowEngine,
        monitor: WorkflowMonitor,
    ) -> None:
        wf = Workflow(
            name="tool-fail",
            steps=[
                WorkflowStep(
                    step_id="doomed",
                    type=StepType.TOOL,
                    target="boom",
                    output_keys=["text"],
                )
            ],
        )
        result = await engine.run(wf)
        monitor.record(result)
        assert result.state == WorkflowState.FAILED
        assert "tool boom" in (result.history[0].error or "").lower() or \
            "boom" in (result.history[0].error or "").lower()
        stats = monitor.get_stats()
        assert stats.failed == 1


# ---------------------------------------------------------------------------
# Engine + Registry + Persistence
# ---------------------------------------------------------------------------


class TestRegistryPersistenceIntegration:
    def test_workflow_round_trip_through_disk(
        self,
        engine: WorkflowEngine,
        tmp_path: Path,
    ) -> None:
        wf = Workflow(
            name="greet",
            description="a workflow for testing",
            metadata={"owner": "tester"},
            variables={"who": "world"},
            steps=[
                WorkflowStep(
                    step_id="g",
                    type=StepType.TOOL,
                    target="shout",
                    inputs={"text": "hello {{ variables.who }}"},
                    output_keys=["text"],
                )
            ],
            outputs={"greeting": "outputs.g.text"},
        )
        reg = WorkflowRegistry()
        v = reg.register(wf)
        assert v == 1

        # Persist the registry's workflows to disk.
        path = tmp_path / "workflows.json"
        save_workflow(reg.list_workflows(), path)

        # Reload from disk.
        loaded = load_workflow(path)
        assert isinstance(loaded, list)
        assert len(loaded) == 1
        assert loaded[0].name == "greet"

        # Run it through the engine.
        result = asyncio.run(engine.run(loaded[0]))
        assert result.state == WorkflowState.COMPLETED
        assert result.outputs["greeting"] == "HELLO WORLD"


class TestResultPersistenceIntegration:
    @pytest.mark.asyncio
    async def test_save_and_load_result(
        self,
        engine: WorkflowEngine,
        tmp_path: Path,
    ) -> None:
        wf = Workflow(
            name="simple",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 2},
                    output_keys=["sum"],
                )
            ],
            outputs={"total": "outputs.s1.sum"},
        )
        result = await engine.run(wf)
        path = tmp_path / "result.json"
        save_result(result, path)
        loaded = load_workflow.__wrapped__ if False else None  # placeholder
        # Use the right import for the result loader.
        from workflows.persistence import load_result

        restored = load_result(path)
        assert restored.state == WorkflowState.COMPLETED
        assert restored.outputs == {"total": 3}
        assert restored.history[0].step_id == "s1"


# ---------------------------------------------------------------------------
# Engine + Validation + Registry
# ---------------------------------------------------------------------------


class TestValidationRegistryIntegration:
    def test_validator_blocks_run_for_unknown_agent(
        self,
        dispatcher: AgentDispatcher,
        tool_orchestrator: ToolOrchestrator,
        engine: WorkflowEngine,
        monitor: WorkflowMonitor,
    ) -> None:
        # Workflow references a non-registered agent.
        wf = Workflow(
            name="needs-ghost",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.AGENT,
                    target="writing",  # not in dispatcher
                )
            ],
        )
        validator = WorkflowValidator(dispatcher=dispatcher)
        result = validator.validate(wf)
        assert result.valid is False
        assert any("unregistered agent" in e for e in result.errors)

        # The Registry stores the workflow but refuses to "advertise"
        # it as runnable — engine still attempts and fails, which
        # is the desired behavior: validation surfaces the issue
        # before the engine does.
        reg = WorkflowRegistry()
        reg.register(wf)

        run_result = asyncio.run(engine.run(reg.get("needs-ghost")))
        monitor.record(run_result)
        assert run_result.state == WorkflowState.FAILED

    def test_validate_many_for_a_library(
        self,
        dispatcher: AgentDispatcher,
    ) -> None:
        wfs = [
            Workflow(
                name="good1",
                steps=[
                    WorkflowStep(
                        step_id="s1",
                        type=StepType.AGENT,
                        target="research",
                    )
                ],
            ),
            Workflow(
                name="bad1",
                steps=[
                    WorkflowStep(
                        step_id="a",
                        type=StepType.AGENT,
                        target="research",
                        depends_on=["b"],
                    ),
                    WorkflowStep(
                        step_id="b",
                        type=StepType.AGENT,
                        target="research",
                        depends_on=["a"],
                    ),
                ],
            ),
        ]
        validator = WorkflowValidator(dispatcher=dispatcher)
        results = validator  # alias
        # Use validate_many via the public helper.
        from workflows.validation import validate_many

        results_map = validate_many(wfs, validator=results)
        assert results_map["good1"].valid is True
        assert results_map["bad1"].valid is False


# ---------------------------------------------------------------------------
# Engine + Monitoring end-to-end
# ---------------------------------------------------------------------------


class TestMonitoringIntegration:
    @pytest.mark.asyncio
    async def test_monitor_records_run_outcomes(
        self,
        engine: WorkflowEngine,
        monitor: WorkflowMonitor,
    ) -> None:
        # Two runs — one succeeds, one fails.
        good = Workflow(
            name="good",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 1},
                    output_keys=["sum"],
                )
            ],
        )
        bad = Workflow(
            name="bad",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.TOOL,
                    target="boom",
                )
            ],
        )
        monitor.record(await engine.run(good))
        monitor.record(await engine.run(bad))
        stats = monitor.get_stats()
        assert stats.total == 2
        assert stats.completed == 1
        assert stats.failed == 1
        assert stats.active == 0
        assert stats.average_duration_ms > 0

    @pytest.mark.asyncio
    async def test_active_tracking(
        self,
        engine: WorkflowEngine,
        monitor: WorkflowMonitor,
    ) -> None:
        monitor.mark_active("wf-x")
        monitor.mark_active("wf-y")
        assert sorted(monitor.get_active()) == ["wf-x", "wf-y"]
        result = await engine.run(
            Workflow(
                name="one",
                steps=[
                    WorkflowStep(
                        step_id="s1",
                        type=StepType.TOOL,
                        target="add",
                        inputs={"a": 1, "b": 1},
                    )
                ],
            )
        )
        monitor.record(result)
        # The recorded workflow is no longer active.
        assert result.workflow_id not in monitor.get_active()
        # The other still-active id remains.
        assert "wf-y" in monitor.get_active()
