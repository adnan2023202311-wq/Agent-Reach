"""Unit tests for the AgentReach SDK (M6.14)."""

from __future__ import annotations

import pytest

from config.settings import Settings, get_settings
from sdk import AgentReach, AgentReachResult


@pytest.fixture(autouse=True)
def _clear_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def sdk():
    with AgentReach(config={"anthropic_api_key": "test-key-for-sdk"}) as app:
        yield app


class TestAgentReachResult:
    def test_creation(self) -> None:
        result = AgentReachResult(answer="Hello", status="succeeded")
        assert result.answer == "Hello"
        assert result.status == "succeeded"
        assert result.results == []

    def test_repr(self) -> None:
        result = AgentReachResult(answer="A" * 100, status="succeeded")
        r = repr(result)
        assert "succeeded" in r
        assert "..." in r


class TestAgentReachInit:
    def test_in_process_mode(self) -> None:
        app = AgentReach(config={"anthropic_api_key": "test-key"})
        assert app._conversation_engine is not None
        assert app._session_manager is not None
        assert app._http_client is None
        app.close()

    def test_with_memory_window(self) -> None:
        app = AgentReach(
            config={"anthropic_api_key": "test-key"},
            memory_window=5,
        )
        assert app._memory_window == 5
        app.close()

    def test_with_user_id(self) -> None:
        app = AgentReach(
            config={"anthropic_api_key": "test-key"},
            user_id="user-1",
        )
        assert app._user_id == "user-1"
        app.close()


class TestAgentReachRun:
    def test_run_returns_result(self, sdk: AgentReach) -> None:
        result = sdk.run("Hello world")
        assert isinstance(result, AgentReachResult)
        assert result.status in ("succeeded", "failed")
        assert result.session_id

    def test_run_with_session(self, sdk: AgentReach) -> None:
        # First turn.
        result1 = sdk.run("First message")
        session_id = result1.session_id
        # Second turn with same session.
        result2 = sdk.run("Second message", session_id=session_id)
        assert result2.session_id == session_id

    def test_run_with_context(self, sdk: AgentReach) -> None:
        result = sdk.run("Hello", context={"tone": "formal"})
        assert isinstance(result, AgentReachResult)


class TestAgentReachSessions:
    def test_new_session(self, sdk: AgentReach) -> None:
        session_id = sdk.new_session()
        assert session_id

    def test_new_session_with_user(self, sdk: AgentReach) -> None:
        session_id = sdk.new_session(user_id="alice")
        assert session_id

    def test_get_history(self, sdk: AgentReach) -> None:
        result = sdk.run("Hello")
        history = sdk.get_history(result.session_id)
        assert len(history) == 2  # user + assistant

    def test_close_session(self, sdk: AgentReach) -> None:
        session_id = sdk.new_session()
        assert sdk.close_session(session_id) is True

    def test_close_session_missing(self, sdk: AgentReach) -> None:
        assert sdk.close_session("ghost") is False


class TestAgentReachContextManager:
    def test_context_manager(self) -> None:
        with AgentReach(config={"anthropic_api_key": "test-key"}) as app:
            result = app.run("Hello")
            assert isinstance(result, AgentReachResult)
