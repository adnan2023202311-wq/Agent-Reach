"""Tests for M9.29 — Multi-Agent Collaboration Engine.

Proves: dependency-wave scheduling that finally honors
SubTask.depends_on (parallel within a wave — verified by real
concurrency), loud failure on unknown/cyclic deps, shared reasoning
through the real M3 AgentMessenger, MOA-rule consensus, explicit
conflict resolution preserving losing outputs, and the API.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from config.settings import get_settings
from core.collaboration_engine import CollaborationEngine
from core.dispatcher import AgentDispatcher
from domain.interfaces import Agent, Planner
from domain.models import AgentType, RetryPolicy, SubTask, TaskPlan


class _ScriptedPlanner(Planner):
    """Planner returning a fixed plan."""

    def __init__(self, plan: TaskPlan) -> None:
        self._plan = plan

    async def create_plan(self, request: str) -> TaskPlan:
        return self._plan


class _TrackingAgent(Agent):
    """Agent that records concurrency and returns a scripted output."""

    active = 0
    max_active = 0

    def __init__(self, agent_type: AgentType, output: str, delay: float = 0.01) -> None:
        self._agent_type = agent_type
        self._output = output
        self._delay = delay

    @property
    def agent_type(self) -> AgentType:
        return self._agent_type

    async def execute(self, subtask: SubTask) -> Any:
        _TrackingAgent.active += 1
        _TrackingAgent.max_active = max(
            _TrackingAgent.max_active, _TrackingAgent.active
        )
        await asyncio.sleep(self._delay)
        _TrackingAgent.active -= 1
        return f"{self._output}:{subtask.id}"


def _engine(plan: TaskPlan, outputs: dict[AgentType, str]) -> CollaborationEngine:
    _TrackingAgent.active = 0
    _TrackingAgent.max_active = 0
    agents = {t: _TrackingAgent(t, out) for t, out in outputs.items()}
    dispatcher = AgentDispatcher(
        agents=agents,
        retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0.0, timeout_seconds=5.0),
    )
    return CollaborationEngine(_ScriptedPlanner(plan), dispatcher)


def _plan(*subtasks: SubTask) -> TaskPlan:
    return TaskPlan(original_request="test", subtasks=list(subtasks))


# ===========================================================================
# Waves & parallelism
# ===========================================================================


@pytest.mark.asyncio
class TestWaves:
    async def test_independent_subtasks_run_in_parallel(self) -> None:
        plan = _plan(
            SubTask(id="a", agent_type=AgentType.RESEARCH, description="a"),
            SubTask(id="b", agent_type=AgentType.CODING, description="b"),
        )
        engine = _engine(plan, {AgentType.RESEARCH: "r", AgentType.CODING: "c"})
        record = await engine.collaborate("do things")
        assert record.waves == [["a", "b"]]
        assert _TrackingAgent.max_active == 2  # genuinely concurrent

    async def test_depends_on_finally_honored(self) -> None:
        plan = _plan(
            SubTask(id="research", agent_type=AgentType.RESEARCH, description="r"),
            SubTask(
                id="code",
                agent_type=AgentType.CODING,
                description="c",
                depends_on=["research"],
            ),
        )
        engine = _engine(plan, {AgentType.RESEARCH: "r", AgentType.CODING: "c"})
        record = await engine.collaborate("dependent work")
        assert record.waves == [["research"], ["code"]]
        assert _TrackingAgent.max_active == 1  # sequential across waves

    async def test_diamond_dependency_waves(self) -> None:
        plan = _plan(
            SubTask(id="root", agent_type=AgentType.RESEARCH, description="root"),
            SubTask(id="left", agent_type=AgentType.CODING, description="l",
                    depends_on=["root"]),
            SubTask(id="right", agent_type=AgentType.RESEARCH, description="r",
                    depends_on=["root"]),
            SubTask(id="merge", agent_type=AgentType.CODING, description="m",
                    depends_on=["left", "right"]),
        )
        engine = _engine(plan, {AgentType.RESEARCH: "r", AgentType.CODING: "c"})
        record = await engine.collaborate("diamond")
        assert record.waves == [["root"], ["left", "right"], ["merge"]]
        assert len(record.results) == 4

    async def test_unknown_dependency_fails_loudly(self) -> None:
        plan = _plan(
            SubTask(id="a", agent_type=AgentType.RESEARCH, description="a",
                    depends_on=["ghost"]),
        )
        engine = _engine(plan, {AgentType.RESEARCH: "r"})
        with pytest.raises(ValueError, match="unknown subtasks"):
            await engine.collaborate("broken")

    async def test_cycle_fails_loudly(self) -> None:
        plan = _plan(
            SubTask(id="a", agent_type=AgentType.RESEARCH, description="a",
                    depends_on=["b"]),
            SubTask(id="b", agent_type=AgentType.CODING, description="b",
                    depends_on=["a"]),
        )
        engine = _engine(plan, {AgentType.RESEARCH: "r", AgentType.CODING: "c"})
        with pytest.raises(ValueError, match="cycle"):
            await engine.collaborate("cyclic")

    async def test_empty_request_rejected(self) -> None:
        engine = _engine(_plan(), {})
        with pytest.raises(ValueError):
            await engine.collaborate("   ")


# ===========================================================================
# Shared reasoning, consensus & conflicts
# ===========================================================================


@pytest.mark.asyncio
class TestReasoningAndConsensus:
    async def test_shared_context_flows_through_real_messenger(self) -> None:
        plan = _plan(
            SubTask(id="up", agent_type=AgentType.RESEARCH, description="u"),
            SubTask(id="down", agent_type=AgentType.CODING, description="d",
                    depends_on=["up"]),
        )
        engine = _engine(plan, {AgentType.RESEARCH: "r", AgentType.CODING: "c"})
        record = await engine.collaborate("share context")
        assert record.shared_messages == 1
        reasoning = engine.get_shared_reasoning(record.collaboration_id)
        assert len(reasoning) == 1
        message = reasoning[0]
        assert message["sender"] == "agent:research"
        assert message["recipient"] == "agent:coding"
        assert "r:up" in message["payload"]["output"]

    async def test_consensus_when_outputs_agree(self) -> None:
        plan = _plan(
            SubTask(id="a", agent_type=AgentType.RESEARCH, description="a"),
        )
        engine = _engine(plan, {AgentType.RESEARCH: "same"})
        record = await engine.collaborate("agree")
        assert record.consensus is True
        assert record.conflicts == []
        assert record.consensus_answer

    async def test_conflict_recorded_and_resolved_explicitly(self) -> None:
        plan = _plan(
            SubTask(id="a", agent_type=AgentType.RESEARCH, description="a"),
            SubTask(id="b", agent_type=AgentType.CODING, description="b"),
        )
        engine = _engine(
            plan, {AgentType.RESEARCH: "answer-one", AgentType.CODING: "answer-two"}
        )
        record = await engine.collaborate("disagree")
        assert record.consensus is False
        assert len(record.conflicts) == 1
        conflict = record.conflicts[0]
        assert conflict["rule"] in ("majority", "latest_wave")
        # losing outputs preserved
        assert len(conflict["options"]) == 2
        assert record.consensus_answer

    async def test_records_listing(self) -> None:
        plan = _plan(
            SubTask(id="a", agent_type=AgentType.RESEARCH, description="a"),
        )
        engine = _engine(plan, {AgentType.RESEARCH: "x"})
        r1 = await engine.collaborate("first")
        r2 = await engine.collaborate("second")
        records = engine.list_records()
        assert [r.collaboration_id for r in records] == [
            r2.collaboration_id, r1.collaboration_id,
        ]
        assert engine.get_record(r1.collaboration_id) is r1


# ===========================================================================
# API
# ===========================================================================


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    import config.settings as settings_module

    original = settings_module.get_settings
    settings_module.get_settings = lambda: settings_module.Settings(
        anthropic_api_key=None,
        default_model_provider="anthropic",
    )
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    settings_module.get_settings = original
    get_settings.cache_clear()


class TestCollaborationAPI:
    def test_collaborate_end_to_end(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/agents/collaborate",
            json={"request": "Research the topic and write code for it"},
        )
        assert resp.status_code == 200
        record = resp.json()
        assert record["status"] == "succeeded"
        assert record["plan_id"]
        assert len(record["results"]) >= 1

    def test_records_and_detail(self, client: TestClient) -> None:
        created = client.post(
            "/api/v1/agents/collaborate", json={"request": "collaborate now"}
        ).json()
        listing = client.get("/api/v1/agents/collaborate/records").json()
        assert listing["count"] >= 1
        detail = client.get(
            f"/api/v1/agents/collaborate/records/{created['collaboration_id']}"
        )
        assert detail.status_code == 200

    def test_reasoning_endpoint(self, client: TestClient) -> None:
        created = client.post(
            "/api/v1/agents/collaborate", json={"request": "reason together"}
        ).json()
        resp = client.get(
            f"/api/v1/agents/collaborate/records/{created['collaboration_id']}/reasoning"
        )
        assert resp.status_code == 200

    def test_unknown_record_404(self, client: TestClient) -> None:
        assert (
            client.get("/api/v1/agents/collaborate/records/ghost").status_code
            == 404
        )

    def test_validation_422(self, client: TestClient) -> None:
        assert (
            client.post(
                "/api/v1/agents/collaborate", json={"request": ""}
            ).status_code
            == 422
        )
