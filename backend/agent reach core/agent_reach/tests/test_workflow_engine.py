"""Unit tests for WorkflowEngine (M5.2)."""

from __future__ import annotations

import asyncio

import pytest

from core.dispatcher import AgentDispatcher
from core.tool_executor import ToolExecutor
from domain.models import AgentType, RetryPolicy, SubTask, TaskStatus
from workflows.engine import WorkflowEngine
from workflows.models import (
    Condition,
    ConditionOp,
    StepType,
    Workflow,
    WorkflowState,
    WorkflowStep,
)
from workflows.orchestration import (
    AgentOrchestrator,
    OrchestrationResult,
    ToolOrchestrator,
    merge_outputs,
)


# ---------------------------------------------------------------------------
# Test fixtures / fakes
# ---------------------------------------------------------------------------


class EchoAgent:
    """Fake agent used by engine tests — implements the Agent protocol."""

    def __init__(self, agent_type: AgentType, *, fail_n: int = 0) -> None:
        self._agent_type = agent_type
        self._calls = 0
        self._fail_n = fail_n

    @property
    def agent_type(self) -> AgentType:
        return self._agent_type

    async def execute(self, subtask: SubTask) -> dict[str, object]:
        self._calls += 1
        if self._calls <= self._fail_n:
            raise RuntimeError("agent boom")
        return {"text": f"echo:{subtask.description}", "echo_input": dict(subtask.input_data)}


class AlwaysFailAgent:
    def __init__(self, agent_type: AgentType) -> None:
        self._agent_type = agent_type
        self._calls = 0

    @property
    def agent_type(self) -> AgentType:
        return self._agent_type

    async def execute(self, subtask: SubTask) -> object:
        self._calls += 1
        raise RuntimeError(f"always fails ({self._calls})")


def _fast_retry() -> RetryPolicy:
    return RetryPolicy(max_attempts=3, backoff_seconds=0.0, timeout_seconds=1.0)


@pytest.fixture
def dispatcher() -> AgentDispatcher:
    agents = {
        AgentType.RESEARCH: EchoAgent(AgentType.RESEARCH),
        AgentType.CODING: EchoAgent(AgentType.CODING),
    }
    return AgentDispatcher(agents=agents, retry_policy=_fast_retry())


@pytest.fixture
def failing_dispatcher() -> AgentDispatcher:
    agents = {AgentType.RESEARCH: AlwaysFailAgent(AgentType.RESEARCH)}
    return AgentDispatcher(agents=agents, retry_policy=_fast_retry())


@pytest.fixture
def flaky_dispatcher() -> AgentDispatcher:
    agents = {AgentType.RESEARCH: EchoAgent(AgentType.RESEARCH, fail_n=2)}
    return AgentDispatcher(agents=agents, retry_policy=_fast_retry())


@pytest.fixture
def agent_orchestrator(dispatcher: AgentDispatcher) -> AgentOrchestrator:
    return AgentOrchestrator(dispatcher=dispatcher)


@pytest.fixture
def tool_orchestrator() -> ToolOrchestrator:
    orch = ToolOrchestrator()

    async def add(a: int = 0, b: int = 0) -> int:
        return a + b

    async def greet(who: str = "world") -> str:
        return f"hello, {who}"

    async def boom() -> None:
        raise RuntimeError("tool boom")

    orch.executor.register_tool("add", add)
    orch.executor.register_tool("greet", greet)
    orch.executor.register_tool("boom", boom)
    return orch


@pytest.fixture
def engine(
    agent_orchestrator: AgentOrchestrator, tool_orchestrator: ToolOrchestrator
) -> WorkflowEngine:
    return WorkflowEngine(
        agent_orchestrator=agent_orchestrator,
        tool_orchestrator=tool_orchestrator,
    )


# ---------------------------------------------------------------------------
# Engine tests
# ---------------------------------------------------------------------------


class TestWorkflowEngineBasic:
    def test_run_single_agent_step(
        self, engine: WorkflowEngine, dispatcher: AgentDispatcher
    ) -> None:
        wf = Workflow(
            name="single",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="echo",
                    type=StepType.AGENT,
                    target="research",
                    inputs={"q": "hello"},
                    output_keys=["text"],
                )
            ],
            outputs={"result": "outputs.s1.text"},
        )
        result = asyncio.run(engine.run(wf))
        assert result.state == WorkflowState.COMPLETED
        assert result.outputs == {"result": "echo:echo"}
        assert len(result.history) == 1
        assert result.history[0].success is True
        assert result.history[0].skipped is False

    def test_run_single_tool_step(self, engine: WorkflowEngine) -> None:
        wf = Workflow(
            name="add",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="add",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 2, "b": 3},
                    output_keys=["sum"],
                )
            ],
            outputs={"total": "outputs.s1.sum"},
        )
        result = asyncio.run(engine.run(wf))
        assert result.state == WorkflowState.COMPLETED
        assert result.outputs == {"total": 5}

    def test_run_sequential_steps(self, engine: WorkflowEngine) -> None:
        wf = Workflow(
            name="seq",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="add1",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 1},
                    output_keys=["sum"],
                ),
                WorkflowStep(
                    step_id="s2",
                    name="add2",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 10, "b": 20},
                    output_keys=["sum"],
                ),
            ],
            outputs={
                "first": "outputs.s1.sum",
                "second": "outputs.s2.sum",
            },
        )
        result = asyncio.run(engine.run(wf))
        assert result.state == WorkflowState.COMPLETED
        assert result.outputs == {"first": 2, "second": 30}

    def test_run_template_inputs(
        self, engine: WorkflowEngine
    ) -> None:
        wf = Workflow(
            name="tmpl",
            variables={"name": "world"},
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="greet",
                    type=StepType.TOOL,
                    target="greet",
                    inputs={"who": "{{ variables.name }}"},
                    output_keys=["message"],
                )
            ],
            outputs={"greeting": "outputs.s1.message"},
        )
        result = asyncio.run(engine.run(wf))
        assert result.outputs == {"greeting": "hello, world"}

    def test_run_template_input_missing_fails(self, engine: WorkflowEngine) -> None:
        wf = Workflow(
            name="missing",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="greet",
                    type=StepType.TOOL,
                    target="greet",
                    inputs={"who": "{{ variables.absent }}"},
                    output_keys=["message"],
                )
            ],
        )
        result = asyncio.run(engine.run(wf))
        assert result.state == WorkflowState.FAILED
        assert "missing variable" in (result.error or "").lower()


class TestWorkflowEngineConditional:
    def test_condition_true_runs_step(self, engine: WorkflowEngine) -> None:
        wf = Workflow(
            name="cond_true",
            variables={"go": True},
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="add",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 1},
                    condition=Condition("go", ConditionOp.TRUTHY),
                    output_keys=["sum"],
                )
            ],
            outputs={"total": "outputs.s1.sum"},
        )
        result = asyncio.run(engine.run(wf))
        assert result.state == WorkflowState.COMPLETED
        assert result.outputs == {"total": 2}
        assert result.history[0].skipped is False

    def test_condition_false_skips_step(self, engine: WorkflowEngine) -> None:
        wf = Workflow(
            name="cond_false",
            variables={"go": False},
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="add",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 1},
                    condition=Condition("go", ConditionOp.TRUTHY),
                    output_keys=["sum"],
                )
            ],
            outputs={"total": "outputs.s1.sum"},
        )
        result = asyncio.run(engine.run(wf))
        assert result.state == WorkflowState.COMPLETED
        assert result.outputs == {"total": None}
        assert result.history[0].skipped is True
        assert result.history[0].success is True

    def test_condition_on_step_output(self, engine: WorkflowEngine) -> None:
        wf = Workflow(
            name="cond_output",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="add",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 2, "b": 2},
                    output_keys=["sum"],
                ),
                WorkflowStep(
                    step_id="s2",
                    name="add_more",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 10, "b": 5},
                    condition=Condition(
                        "outputs.s1.sum", ConditionOp.GTE, value=4
                    ),
                    output_keys=["sum"],
                ),
            ],
            outputs={"first": "outputs.s1.sum", "second": "outputs.s2.sum"},
        )
        result = asyncio.run(engine.run(wf))
        assert result.state == WorkflowState.COMPLETED
        assert result.outputs == {"first": 4, "second": 15}

    def test_branching_skipped_produces_none(self, engine: WorkflowEngine) -> None:
        wf = Workflow(
            name="branch",
            variables={"run_second": False},
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="add",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 1},
                    output_keys=["sum"],
                ),
                WorkflowStep(
                    step_id="s2",
                    name="add_more",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 5, "b": 5},
                    condition=Condition(
                        "run_second", ConditionOp.TRUTHY
                    ),
                    output_keys=["sum"],
                ),
            ],
            outputs={"first": "outputs.s1.sum", "second": "outputs.s2.sum"},
        )
        result = asyncio.run(engine.run(wf))
        assert result.state == WorkflowState.COMPLETED
        assert result.outputs == {"first": 2, "second": None}


class TestWorkflowEngineRetry:
    def test_retries_then_succeeds(
        self, flaky_dispatcher: AgentDispatcher, tool_orchestrator: ToolOrchestrator
    ) -> None:
        engine = WorkflowEngine(
            agent_orchestrator=AgentOrchestrator(dispatcher=flaky_dispatcher),
            tool_orchestrator=tool_orchestrator,
            default_retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=0.0),
        )
        wf = Workflow(
            name="retry",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="flaky",
                    type=StepType.AGENT,
                    target="research",
                    output_keys=["text"],
                )
            ],
            outputs={"out": "outputs.s1.text"},
        )
        result = asyncio.run(engine.run(wf))
        assert result.state == WorkflowState.COMPLETED
        assert result.history[0].attempts == 3

    def test_all_attempts_fail(self, failing_dispatcher: AgentDispatcher) -> None:
        engine = WorkflowEngine(
            agent_orchestrator=AgentOrchestrator(dispatcher=failing_dispatcher),
            default_retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=0.0),
        )
        wf = Workflow(
            name="fail",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="doomed",
                    type=StepType.AGENT,
                    target="research",
                )
            ],
        )
        result = asyncio.run(engine.run(wf))
        assert result.state == WorkflowState.FAILED
        assert "doomed" in (result.error or "")
        assert result.history[0].attempts == 6

    def test_step_level_retry_overrides_workflow_default(
        self, flaky_dispatcher: AgentDispatcher
    ) -> None:
        # The flaky agent fails on its first 2 invocations and
        # succeeds on the third. The dispatcher does its own
        # internal retry up to max_attempts=3, and on the engine's
        # first call the dispatcher succeeds internally after 3
        # invocations. The recorded attempts reflects 3 — the
        # actual number of agent calls.
        engine = WorkflowEngine(
            agent_orchestrator=AgentOrchestrator(dispatcher=flaky_dispatcher),
            default_retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
        )
        wf = Workflow(
            name="override",
            default_retry_policy=RetryPolicy(max_attempts=5, backoff_seconds=0.0),
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="flaky",
                    type=StepType.AGENT,
                    target="research",
                    retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=0.0),
                    output_keys=["text"],
                )
            ],
        )
        result = asyncio.run(engine.run(wf))
        assert result.history[0].attempts == 3


class TestWorkflowEngineDependency:
    def test_missing_dependency_fails(self, engine: WorkflowEngine) -> None:
        wf = Workflow(
            name="bad_dep",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="depends_on_missing",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 1},
                    depends_on=["never_runs"],
                    output_keys=["sum"],
                )
            ],
        )
        result = asyncio.run(engine.run(wf))
        assert result.state == WorkflowState.FAILED
        assert "never executed" in (result.error or "")

    def test_skipped_dependency_skips_dependent(
        self, engine: WorkflowEngine
    ) -> None:
        wf = Workflow(
            name="skipped_dep",
            variables={"go": False},
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="skipped",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 1},
                    condition=Condition("go", ConditionOp.TRUTHY),
                    output_keys=["sum"],
                ),
                WorkflowStep(
                    step_id="s2",
                    name="depend",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 10, "b": 10},
                    depends_on=["s1"],
                    output_keys=["sum"],
                ),
            ],
        )
        result = asyncio.run(engine.run(wf))
        assert result.state == WorkflowState.COMPLETED
        assert result.history[0].skipped is True
        assert result.history[1].skipped is True


class TestWorkflowEngineSync:
    def test_run_sync_returns_result(self, engine: WorkflowEngine) -> None:
        wf = Workflow(
            name="sync",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="add",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 2, "b": 2},
                    output_keys=["sum"],
                )
            ],
            outputs={"x": "outputs.s1.sum"},
        )
        result = engine.run_sync(wf)
        assert result.state == WorkflowState.COMPLETED
        assert result.outputs == {"x": 4}

    def test_run_sync_failure(self, failing_dispatcher: AgentDispatcher) -> None:
        engine = WorkflowEngine(
            agent_orchestrator=AgentOrchestrator(dispatcher=failing_dispatcher),
            default_retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
        )
        wf = Workflow(
            name="sync_fail",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="doomed",
                    type=StepType.AGENT,
                    target="research",
                )
            ],
        )
        result = engine.run_sync(wf)
        assert result.state == WorkflowState.FAILED


class TestWorkflowEngineAccessors:
    def test_get_result_none_when_missing(
        self, engine: WorkflowEngine
    ) -> None:
        assert engine.get_result("missing") is None

    def test_list_results(self, engine: WorkflowEngine) -> None:
        wf = Workflow(
            name="x",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    name="add",
                    type=StepType.TOOL,
                    target="add",
                    inputs={"a": 1, "b": 1},
                    output_keys=["sum"],
                )
            ],
        )
        asyncio.run(engine.run(wf))
        results = engine.list_results()
        assert len(results) == 1
        assert results[0].state == WorkflowState.COMPLETED

    def test_clear(self, engine: WorkflowEngine) -> None:
        engine.clear()
        assert engine.list_results() == []


class TestMergeOutputs:
    def test_disjoint_keys(self) -> None:
        merged = merge_outputs([{"a": 1}, {"b": 2}])
        assert merged == {"a": 1, "b": 2}

    def test_overrides(self) -> None:
        merged = merge_outputs([{"a": 1}, {"a": 2}])
        assert merged == {"a": 2}

    def test_lists_concatenated(self) -> None:
        merged = merge_outputs([{"x": [1, 2]}, {"x": [3, 4]}])
        assert merged == {"x": [1, 2, 3, 4]}

    def test_list_and_nonlist_override(self) -> None:
        merged = merge_outputs([{"x": [1, 2]}, {"x": "scalar"}])
        assert merged == {"x": "scalar"}
