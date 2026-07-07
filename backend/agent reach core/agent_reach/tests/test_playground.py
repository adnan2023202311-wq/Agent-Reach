"""Unit tests for Playground (M6.7)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from core.controller import MainController
from core.dispatcher import AgentDispatcher
from core.planner import RuleBasedPlanner
from domain.interfaces import Agent
from domain.models import AgentType, RetryPolicy, SubTask
from playground import Playground
from conversation.session_manager import SessionManager
from conversation.engine import ConversationEngine
from workflows.engine import WorkflowEngine
from workflows.registry import WorkflowRegistry
from workflows.models import StepType, Workflow, WorkflowStep


class EchoAgent(Agent):
    def __init__(self, agent_type: AgentType) -> None:
        self._agent_type = agent_type

    @property
    def agent_type(self) -> AgentType:
        return self._agent_type

    async def execute(self, subtask: SubTask) -> Any:
        return f"echo:{subtask.description}"


@pytest.fixture
def controller() -> MainController:
    agents = {t: EchoAgent(t) for t in (AgentType.RESEARCH, AgentType.CODING)}
    dispatcher = AgentDispatcher(
        agents=agents,
        retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0.0, timeout_seconds=1.0),
    )
    return MainController(planner=RuleBasedPlanner(), dispatcher=dispatcher)


@pytest.fixture
def conversation_engine(controller: MainController) -> ConversationEngine:
    return ConversationEngine(
        controller=controller,
        session_manager=SessionManager(),
    )


@pytest.fixture
def workflow_engine(controller: MainController) -> WorkflowEngine:
    from workflows.orchestration import AgentOrchestrator, ToolOrchestrator
    return WorkflowEngine(
        agent_orchestrator=AgentOrchestrator(dispatcher=controller._dispatcher),
        tool_orchestrator=ToolOrchestrator(),
    )


@pytest.fixture
def workflow_registry() -> WorkflowRegistry:
    return WorkflowRegistry()


@pytest.fixture
def playground(
    controller: MainController,
    conversation_engine: ConversationEngine,
    workflow_engine: WorkflowEngine,
    workflow_registry: WorkflowRegistry,
) -> Playground:
    return Playground(
        controller=controller,
        conversation_engine=conversation_engine,
        workflow_engine=workflow_engine,
        workflow_registry=workflow_registry,
    )


class TestInspectPlan:
    def test_inspect_plan(self, playground: Playground) -> None:
        result = playground.inspect_plan("research the latest AI developments")
        assert "plan_id" in result
        assert result["original_request"] == "research the latest AI developments"
        assert result["subtask_count"] > 0
        assert len(result["subtasks"]) == result["subtask_count"]

    def test_inspect_plan_subtask_structure(self, playground: Playground) -> None:
        result = playground.inspect_plan("test request")
        for st in result["subtasks"]:
            assert "id" in st
            assert "agent_type" in st
            assert "description" in st


class TestInspectRuntime:
    def test_inspect_runtime(self, playground: Playground) -> None:
        result = playground.inspect_runtime()
        assert "registered_agents" in result
        assert result["agent_count"] > 0
        assert "research" in result["registered_agents"]


class TestInspectSessions:
    def test_inspect_sessions_empty(self, playground: Playground) -> None:
        result = playground.inspect_sessions()
        assert result == []

    def test_inspect_sessions_with_data(self, playground: Playground) -> None:
        session = playground._conversation_engine._session_manager.create_session(
            user_id="u1"
        )
        result = playground.inspect_sessions()
        assert len(result) == 1
        assert result[0]["session_id"] == session.session_id


class TestInspectMemory:
    def test_inspect_memory_summary(self, playground: Playground) -> None:
        result = playground.inspect_memory()
        assert "session_count" in result

    def test_inspect_memory_for_session(self, playground: Playground) -> None:
        session = playground._conversation_engine._session_manager.create_session()
        result = playground.inspect_memory(session.session_id)
        assert result["session_id"] == session.session_id
        assert result["message_count"] == 0


class TestWorkflowExecution:
    def test_list_workflows_empty(self, playground: Playground) -> None:
        result = playground.list_workflows()
        assert result == []

    def test_list_workflows_populated(self, playground: Playground) -> None:
        wf = Workflow(name="test", steps=[WorkflowStep(step_id="s1")])
        playground._workflow_registry.register(wf)
        result = playground.list_workflows()
        assert len(result) == 1
        assert result[0]["name"] == "test"

    def test_execute_workflow(self, playground: Playground) -> None:
        wf = Workflow(
            name="exec-test",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.AGENT,
                    target="research",
                    inputs={"q": "hello"},
                    output_keys=["text"],
                )
            ],
        )
        result = playground.execute_workflow(wf)
        assert "state" in result
        assert result["state"] in ("completed", "failed")


class TestExecutionHistory:
    def test_inspect_execution_history_empty(self, playground: Playground) -> None:
        result = playground.inspect_execution_history()
        assert result == []

    def test_inspect_execution_history_with_data(self, playground: Playground) -> None:
        wf = Workflow(
            name="hist-test",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.AGENT,
                    target="research",
                    inputs={"q": "hi"},
                    output_keys=["text"],
                )
            ],
        )
        playground.execute_workflow(wf)
        result = playground.inspect_execution_history()
        assert len(result) >= 1

    def test_get_execution_result(self, playground: Playground) -> None:
        wf = Workflow(
            name="result-test",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    type=StepType.AGENT,
                    target="research",
                    inputs={"q": "hi"},
                    output_keys=["text"],
                )
            ],
        )
        exec_result = playground.execute_workflow(wf)
        fetched = playground.get_execution_result(exec_result["workflow_id"])
        assert fetched is not None
        assert fetched["workflow_id"] == exec_result["workflow_id"]

    def test_get_execution_result_missing(self, playground: Playground) -> None:
        assert playground.get_execution_result("ghost") is None
