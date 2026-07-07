"""Unit tests for SessionManager (M6.2)."""

from __future__ import annotations

import pytest

from conversation.session_manager import (
    InMemorySessionStore,
    Session,
    SessionManager,
    SessionState,
)


# ---------------------------------------------------------------------------
# Session model
# ---------------------------------------------------------------------------


class TestSessionModel:
    def test_default_session_has_uuid_and_active_state(self) -> None:
        s = Session()
        assert s.session_id
        assert s.state is SessionState.ACTIVE
        assert s.user_id == ""
        assert s.metadata == {}

    def test_session_to_dict_round_trip(self) -> None:
        s = Session(user_id="u1", metadata={"k": "v"})
        data = s.to_dict()
        restored = Session.from_dict(data)
        assert restored.session_id == s.session_id
        assert restored.user_id == "u1"
        assert restored.state is SessionState.ACTIVE
        assert restored.metadata == {"k": "v"}

    def test_session_from_dict_unknown_state_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown SessionState"):
            Session.from_dict({"session_id": "x", "state": "bogus"})

    def test_session_from_dict_non_dict_raises(self) -> None:
        with pytest.raises(ValueError, match="must be a dict"):
            Session.from_dict("not-a-dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# InMemorySessionStore
# ---------------------------------------------------------------------------


class TestInMemorySessionStore:
    def test_save_and_load(self) -> None:
        store = InMemorySessionStore()
        s = Session(session_id="abc")
        store.save(s)
        assert store.load("abc") is s

    def test_load_missing_returns_none(self) -> None:
        store = InMemorySessionStore()
        assert store.load("missing") is None

    def test_delete_existing(self) -> None:
        store = InMemorySessionStore()
        store.save(Session(session_id="abc"))
        assert store.delete("abc") is True
        assert store.load("abc") is None

    def test_delete_missing(self) -> None:
        store = InMemorySessionStore()
        assert store.delete("missing") is False

    def test_list_all(self) -> None:
        store = InMemorySessionStore()
        s1 = Session(session_id="a")
        s2 = Session(session_id="b")
        store.save(s1)
        store.save(s2)
        assert store.list_all() == [s1, s2]

    def test_clear(self) -> None:
        store = InMemorySessionStore()
        store.save(Session(session_id="a"))
        store.clear()
        assert store.list_all() == []


# ---------------------------------------------------------------------------
# SessionManager lifecycle
# ---------------------------------------------------------------------------


class TestSessionManagerLifecycle:
    def test_create_session_returns_active_session(self) -> None:
        mgr = SessionManager()
        s = mgr.create_session(user_id="u1", metadata={"source": "test"})
        assert s.state is SessionState.ACTIVE
        assert s.user_id == "u1"
        assert s.metadata == {"source": "test"}
        assert s.session_id

    def test_create_session_persists(self) -> None:
        mgr = SessionManager()
        s = mgr.create_session()
        assert mgr.get_session(s.session_id) is s

    def test_get_session_missing_returns_none(self) -> None:
        mgr = SessionManager()
        assert mgr.get_session("nope") is None

    def test_resume_paused_session(self) -> None:
        mgr = SessionManager()
        s = mgr.create_session()
        assert mgr.pause_session(s.session_id) is True
        resumed = mgr.resume_session(s.session_id)
        assert resumed is not None
        assert resumed.state is SessionState.ACTIVE

    def test_resume_terminated_session_returns_none(self) -> None:
        mgr = SessionManager()
        s = mgr.create_session()
        mgr.terminate_session(s.session_id)
        assert mgr.resume_session(s.session_id) is None

    def test_resume_missing_session_returns_none(self) -> None:
        mgr = SessionManager()
        assert mgr.resume_session("ghost") is None

    def test_pause_active_session(self) -> None:
        mgr = SessionManager()
        s = mgr.create_session()
        assert mgr.pause_session(s.session_id) is True
        assert mgr.get_session(s.session_id).state is SessionState.PAUSED

    def test_pause_paused_session_returns_false(self) -> None:
        mgr = SessionManager()
        s = mgr.create_session()
        mgr.pause_session(s.session_id)
        assert mgr.pause_session(s.session_id) is False

    def test_pause_missing_session_returns_false(self) -> None:
        mgr = SessionManager()
        assert mgr.pause_session("ghost") is False

    def test_terminate_session(self) -> None:
        mgr = SessionManager()
        s = mgr.create_session()
        assert mgr.terminate_session(s.session_id) is True
        assert mgr.get_session(s.session_id).state is SessionState.TERMINATED

    def test_terminate_missing_session_returns_false(self) -> None:
        mgr = SessionManager()
        assert mgr.terminate_session("ghost") is False

    def test_delete_session(self) -> None:
        mgr = SessionManager()
        s = mgr.create_session()
        assert mgr.delete_session(s.session_id) is True
        assert mgr.get_session(s.session_id) is None

    def test_delete_missing_session_returns_false(self) -> None:
        mgr = SessionManager()
        assert mgr.delete_session("ghost") is False


# ---------------------------------------------------------------------------
# SessionManager queries
# ---------------------------------------------------------------------------


class TestSessionManagerQueries:
    def test_list_sessions_empty(self) -> None:
        mgr = SessionManager()
        assert mgr.list_sessions() == []

    def test_list_sessions_all(self) -> None:
        mgr = SessionManager()
        s1 = mgr.create_session(user_id="u1")
        s2 = mgr.create_session(user_id="u2")
        result = mgr.list_sessions()
        assert {s.session_id for s in result} == {s1.session_id, s2.session_id}

    def test_list_sessions_filtered_by_user(self) -> None:
        mgr = SessionManager()
        mgr.create_session(user_id="u1")
        s2 = mgr.create_session(user_id="u2")
        result = mgr.list_sessions(user_id="u2")
        assert [s.session_id for s in result] == [s2.session_id]

    def test_list_sessions_by_state(self) -> None:
        mgr = SessionManager()
        s1 = mgr.create_session()
        s2 = mgr.create_session()
        mgr.pause_session(s2.session_id)
        active = mgr.list_sessions_by_state(SessionState.ACTIVE)
        paused = mgr.list_sessions_by_state(SessionState.PAUSED)
        assert [s.session_id for s in active] == [s1.session_id]
        assert [s.session_id for s in paused] == [s2.session_id]

    def test_touch_updates_timestamp(self) -> None:
        mgr = SessionManager()
        s = mgr.create_session()
        original = s.updated_at
        import time as _time

        _time.sleep(0.01)
        assert mgr.touch(s.session_id) is True
        assert mgr.get_session(s.session_id).updated_at > original

    def test_touch_missing_returns_false(self) -> None:
        mgr = SessionManager()
        assert mgr.touch("ghost") is False

    def test_clear(self) -> None:
        mgr = SessionManager()
        mgr.create_session()
        mgr.create_session()
        mgr.clear()
        assert mgr.list_sessions() == []


# ---------------------------------------------------------------------------
# Session isolation
# ---------------------------------------------------------------------------


class TestSessionIsolation:
    def test_sessions_are_isolated_by_id(self) -> None:
        """Operations on one session must not affect another."""
        mgr = SessionManager()
        s1 = mgr.create_session(user_id="u1")
        s2 = mgr.create_session(user_id="u2")

        mgr.terminate_session(s1.session_id)

        assert mgr.get_session(s1.session_id).state is SessionState.TERMINATED
        assert mgr.get_session(s2.session_id).state is SessionState.ACTIVE

    def test_separate_managers_do_not_share_state(self) -> None:
        """Two SessionManager instances with independent stores are isolated."""
        mgr1 = SessionManager()
        mgr2 = SessionManager()
        s1 = mgr1.create_session()
        assert mgr2.get_session(s1.session_id) is None
