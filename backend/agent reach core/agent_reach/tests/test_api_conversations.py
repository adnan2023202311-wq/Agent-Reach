"""Integration tests for /api/v1/conversations endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from config.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    # Create settings with a test API key BEFORE importing create_app.
    settings = Settings(anthropic_api_key="test-key-for-api-tests")
    get_settings.cache_clear()
    # Patch the cached get_settings to return our test settings.
    import config.settings as settings_module
    settings_module.get_settings = lambda: settings
    # Now import create_app — it will use the patched get_settings.
    from api.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


class TestSessions:
    def test_create_session(self, client: TestClient) -> None:
        resp = client.post("/api/v1/conversations/sessions", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["state"] == "active"

    def test_create_session_with_user(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/conversations/sessions",
            json={"user_id": "user-1", "metadata": {"source": "test"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data

    def test_list_sessions(self, client: TestClient) -> None:
        client.post("/api/v1/conversations/sessions", json={"user_id": "u1"})
        client.post("/api/v1/conversations/sessions", json={"user_id": "u1"})
        resp = client.get("/api/v1/conversations/sessions?user_id=u1")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_get_session(self, client: TestClient) -> None:
        create_resp = client.post("/api/v1/conversations/sessions", json={})
        session_id = create_resp.json()["session_id"]
        resp = client.get(f"/api/v1/conversations/sessions/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["session_id"] == session_id

    def test_get_session_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/conversations/sessions/ghost")
        assert resp.status_code == 404


class TestMessages:
    def test_send_message(self, client: TestClient) -> None:
        create_resp = client.post("/api/v1/conversations/sessions", json={})
        session_id = create_resp.json()["session_id"]
        resp = client.post(
            f"/api/v1/conversations/sessions/{session_id}/messages",
            json={"session_id": session_id, "message": "hello"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "assistant"
        assert data["content"]

    def test_send_message_empty_raises(self, client: TestClient) -> None:
        create_resp = client.post("/api/v1/conversations/sessions", json={})
        session_id = create_resp.json()["session_id"]
        resp = client.post(
            f"/api/v1/conversations/sessions/{session_id}/messages",
            json={"session_id": session_id, "message": ""},
        )
        assert resp.status_code == 422  # validation error

    def test_send_message_unknown_session(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/conversations/sessions/ghost/messages",
            json={"session_id": "ghost", "message": "hi"},
        )
        assert resp.status_code == 400

    def test_get_history(self, client: TestClient) -> None:
        create_resp = client.post("/api/v1/conversations/sessions", json={})
        session_id = create_resp.json()["session_id"]
        client.post(
            f"/api/v1/conversations/sessions/{session_id}/messages",
            json={"session_id": session_id, "message": "hi"},
        )
        resp = client.get(f"/api/v1/conversations/sessions/{session_id}/history")
        assert resp.status_code == 200
        history = resp.json()
        assert len(history) == 2  # user + assistant


class TestSessionLifecycle:
    def test_terminate_session(self, client: TestClient) -> None:
        create_resp = client.post("/api/v1/conversations/sessions", json={})
        session_id = create_resp.json()["session_id"]
        resp = client.post(f"/api/v1/conversations/sessions/{session_id}/terminate")
        assert resp.status_code == 200
        # Verify it's terminated.
        get_resp = client.get(f"/api/v1/conversations/sessions/{session_id}")
        assert get_resp.json()["state"] == "terminated"

    def test_delete_session(self, client: TestClient) -> None:
        create_resp = client.post("/api/v1/conversations/sessions", json={})
        session_id = create_resp.json()["session_id"]
        resp = client.delete(f"/api/v1/conversations/sessions/{session_id}")
        assert resp.status_code == 200
        # Verify it's gone.
        get_resp = client.get(f"/api/v1/conversations/sessions/{session_id}")
        assert get_resp.status_code == 404
