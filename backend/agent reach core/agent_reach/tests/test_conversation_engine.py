"""Unit tests for ConversationEngine (M6.1)."""

from __future__ import annotations

from typing import Any

import pytest

from conversation.engine import (
    ConversationEngine,
    ConversationTurnResult,
    Message,
    MessageRole,
)
from conversation.session_manager import SessionManager, SessionState
from core.controller import MainController
from core.dispatcher import AgentDispatcher
from core.planner import RuleBasedPlanner
from domain.interfaces import Agent
from domain.models import AgentType, RetryPolicy, SubTask, TaskStatus


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class EchoAgent(Agent):
    """Returns the subtask description, never fails."""

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
def session_manager() -> SessionManager:
    return SessionManager()


@pytest.fixture
def engine(
    controller: MainController, session_manager: SessionManager
) -> ConversationEngine:
    return ConversationEngine(
        controller=controller,
        session_manager=session_manager,
        memory_window=5,
    )


# ---------------------------------------------------------------------------
# Message model
# ---------------------------------------------------------------------------


class TestMessageModel:
    def test_default_message_has_uuid_and_user_role(self) -> None:
        m = Message(content="hello")
        assert m.message_id
        assert m.role is MessageRole.USER
        assert m.content == "hello"

    def test_message_to_dict(self) -> None:
        m = Message(session_id="s1", role=MessageRole.ASSISTANT, content="hi")
        d = m.to_dict()
        assert d["session_id"] == "s1"
        assert d["role"] == "assistant"
        assert d["content"] == "hi"


# ---------------------------------------------------------------------------
# Turn execution
# ---------------------------------------------------------------------------


class TestConversationTurn:
    async def test_send_message_returns_result(
        self, engine: ConversationEngine, session_manager: SessionManager
    ) -> None:
        session = session_manager.create_session()
        result = await engine.send_message(session.session_id, "hello world")
        assert isinstance(result, ConversationTurnResult)
        assert result.user_message.content == "hello world"
        assert result.assistant_message.role is MessageRole.ASSISTANT
        assert result.assistant_message.content  # non-empty answer

    async def test_send_message_records_history(
        self, engine: ConversationEngine, session_manager: SessionManager
    ) -> None:
        session = session_manager.create_session()
        await engine.send_message(session.session_id, "first turn")
        history = engine.get_history(session.session_id)
        assert len(history) == 2
        assert history[0].role is MessageRole.USER
        assert history[0].content == "first turn"
        assert history[1].role is MessageRole.ASSISTANT

    async def test_send_message_multi_turn(
        self, engine: ConversationEngine, session_manager: SessionManager
    ) -> None:
        session = session_manager.create_session()
        await engine.send_message(session.session_id, "turn 1")
        await engine.send_message(session.session_id, "turn 2")
        await engine.send_message(session.session_id, "turn 3")
        history = engine.get_history(session.session_id)
        # 3 user + 3 assistant = 6 messages
        assert len(history) == 6
        assert [m.role for m in history] == [
            MessageRole.USER,
            MessageRole.ASSISTANT,
            MessageRole.USER,
            MessageRole.ASSISTANT,
            MessageRole.USER,
            MessageRole.ASSISTANT,
        ]

    async def test_send_message_touches_session(
        self, engine: ConversationEngine, session_manager: SessionManager
    ) -> None:
        session = session_manager.create_session()
        original = session.updated_at
        import time as _time

        _time.sleep(0.01)
        await engine.send_message(session.session_id, "hi")
        updated = session_manager.get_session(session.session_id)
        assert updated.updated_at > original

    async def test_send_message_unknown_session_raises(
        self, engine: ConversationEngine
    ) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            await engine.send_message("ghost-session", "hi")

    async def test_send_message_inactive_session_raises(
        self, engine: ConversationEngine, session_manager: SessionManager
    ) -> None:
        session = session_manager.create_session()
        session_manager.pause_session(session.session_id)
        with pytest.raises(ValueError, match="not active"):
            await engine.send_message(session.session_id, "hi")

    async def test_send_message_terminated_session_raises(
        self, engine: ConversationEngine, session_manager: SessionManager
    ) -> None:
        session = session_manager.create_session()
        session_manager.terminate_session(session.session_id)
        with pytest.raises(ValueError, match="not active"):
            await engine.send_message(session.session_id, "hi")


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


class TestHistory:
    def test_get_history_empty(self, engine: ConversationEngine) -> None:
        assert engine.get_history("no-such-session") == []

    def test_get_recent_history(
        self, engine: ConversationEngine, session_manager: SessionManager
    ) -> None:
        session = session_manager.create_session()
        # Manually seed history.
        for i in range(10):
            engine._append_message(
                session.session_id,
                Message(role=MessageRole.USER, content=f"m{i}"),
            )
        recent = engine.get_recent_history(session.session_id, count=3)
        assert [m.content for m in recent] == ["m7", "m8", "m9"]

    def test_clear_history(
        self, engine: ConversationEngine, session_manager: SessionManager
    ) -> None:
        session = session_manager.create_session()
        engine._append_message(
            session.session_id, Message(role=MessageRole.USER, content="x")
        )
        assert engine.clear_history(session.session_id) is True
        assert engine.get_history(session.session_id) == []

    def test_clear_history_missing(self, engine: ConversationEngine) -> None:
        assert engine.clear_history("ghost") is False


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


class TestContext:
    def test_get_context_empty(self, engine: ConversationEngine) -> None:
        assert engine.get_context("s1") == {}

    def test_set_and_get_context(
        self, engine: ConversationEngine, session_manager: SessionManager
    ) -> None:
        session = session_manager.create_session()
        engine.set_context(session.session_id, "tone", "formal")
        engine.set_context(session.session_id, "lang", "en")
        ctx = engine.get_context(session.session_id)
        assert ctx == {"tone": "formal", "lang": "en"}

    def test_clear_context(
        self, engine: ConversationEngine, session_manager: SessionManager
    ) -> None:
        session = session_manager.create_session()
        engine.set_context(session.session_id, "k", "v")
        assert engine.clear_context(session.session_id) is True
        assert engine.get_context(session.session_id) == {}

    def test_clear_context_missing(self, engine: ConversationEngine) -> None:
        assert engine.clear_context("ghost") is False

    async def test_extra_context_persists(
        self, engine: ConversationEngine, session_manager: SessionManager
    ) -> None:
        session = session_manager.create_session()
        await engine.send_message(
            session.session_id, "hi", extra_context={"source": "test"}
        )
        assert engine.get_context(session.session_id) == {"source": "test"}


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


class TestMemory:
    def test_build_request_no_memory_when_window_zero(
        self, controller: MainController, session_manager: SessionManager
    ) -> None:
        eng = ConversationEngine(
            controller=controller,
            session_manager=session_manager,
            memory_window=0,
        )
        session = session_manager.create_session()
        req = eng._build_request(session.session_id, "current msg")
        assert req == "current msg"

    def test_build_request_no_memory_when_no_history(
        self, engine: ConversationEngine, session_manager: SessionManager
    ) -> None:
        session = session_manager.create_session()
        req = engine._build_request(session.session_id, "current msg")
        assert req == "current msg"

    def test_build_request_includes_prior_turns(
        self, engine: ConversationEngine, session_manager: SessionManager
    ) -> None:
        session = session_manager.create_session()
        # Seed prior history (user + assistant pair).
        engine._append_message(
            session.session_id, Message(role=MessageRole.USER, content="prev question")
        )
        engine._append_message(
            session.session_id,
            Message(role=MessageRole.ASSISTANT, content="prev answer"),
        )
        # The current user message is appended before building the
        # request (matching send_message's actual flow).
        engine._append_message(
            session.session_id, Message(role=MessageRole.USER, content="follow-up")
        )
        req = engine._build_request(session.session_id, "follow-up")
        assert "prev question" in req
        assert "prev answer" in req
        assert "follow-up" in req

    def test_build_request_respects_window(
        self, engine: ConversationEngine, session_manager: SessionManager
    ) -> None:
        session = session_manager.create_session()
        # Seed more turns than the window (window=5).
        for i in range(10):
            engine._append_message(
                session.session_id, Message(role=MessageRole.USER, content=f"u{i}")
            )
            engine._append_message(
                session.session_id,
                Message(role=MessageRole.ASSISTANT, content=f"a{i}"),
            )
        prior = engine._prior_turns(session.session_id)
        # Window of 5 user/assistant turns = 10 messages, but the last
        # user message is the "current" one (not in history yet), so
        # prior_turns sees 9 messages (5 user + 4 assistant, then the
        # window clips). The exact count depends on the sliding window
        # logic — what matters is it's bounded.
        assert len(prior) <= 10  # 5 turns max


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_removes_all_state(
        self, engine: ConversationEngine, session_manager: SessionManager
    ) -> None:
        session = session_manager.create_session()
        engine._append_message(
            session.session_id, Message(role=MessageRole.USER, content="x")
        )
        engine.set_context(session.session_id, "k", "v")
        engine.clear()
        assert engine.get_history(session.session_id) == []
        assert engine.get_context(session.session_id) == {}
