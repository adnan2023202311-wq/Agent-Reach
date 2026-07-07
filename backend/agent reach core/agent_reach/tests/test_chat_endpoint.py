"""Regression test for POST /chat endpoint using MockModelClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from config.settings import get_settings


@pytest.fixture(autouse=True)
def _clear_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    import config.settings as settings_module
    original = settings_module.get_settings
    # Ensure no API key is set so MockModelClient is used.
    settings_module.get_settings = lambda: settings_module.Settings(
        anthropic_api_key=None,
        default_model_provider="anthropic",
    )
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    settings_module.get_settings = original
    get_settings.cache_clear()


class TestChatEndpoint:
    def test_chat_returns_200(self, client: TestClient) -> None:
        """POST /api/v1/chat should return 200 with MockModelClient."""
        resp = client.post("/api/v1/chat", json={"message": "Hello world"})
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert "status" in data
        assert data["status"] == "succeeded"
        # MockModelClient should be used (no real API key).
        assert "MockModelClient" in data["answer"]

    def test_chat_returns_plan_id(self, client: TestClient) -> None:
        resp = client.post("/api/v1/chat", json={"message": "Research AI"})
        assert resp.status_code == 200
        data = resp.json()
        assert "plan_id" in data
        assert data["plan_id"]

    def test_chat_with_session_id(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/chat",
            json={"message": "Hello", "session_id": "test-session-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "test-session-123"

    def test_chat_empty_message_returns_422(self, client: TestClient) -> None:
        """Empty message should return 422 validation error."""
        resp = client.post("/api/v1/chat", json={"message": ""})
        assert resp.status_code == 422

    def test_chat_missing_message_returns_422(self, client: TestClient) -> None:
        """Missing message field should return 422."""
        resp = client.post("/api/v1/chat", json={})
        assert resp.status_code == 422
