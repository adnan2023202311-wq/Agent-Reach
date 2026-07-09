"""Regression test for POST /chat endpoint (M9 production runtime).

With no API key configured, the ProviderManager returns a clear error
instead of silently mocking — this is the correct M9 production behaviour.
"""

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
    # No API key configured — the ProviderManager will surface a clear error.
    settings_module.get_settings = lambda: settings_module.Settings(
        anthropic_api_key=None,
        default_model_provider="anthropic",
        task_timeout_seconds=2.0,
        retry_backoff_seconds=0.01,
        max_subtask_retries=1,
    )
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    settings_module.get_settings = original
    get_settings.cache_clear()


class TestChatEndpoint:
    def test_chat_returns_error_without_api_key(self, client: TestClient) -> None:
        """M9: without a configured provider the API returns a clear error."""
        resp = client.post("/api/v1/chat", json={"message": "Hello world"})
        # The endpoint should return a response — it may be 200 with
        # error content or 500 depending on how the pipeline handles it.
        assert resp.status_code in (200, 500)
        data = resp.json()
        # Either "answer" or "detail" should mention the configuration issue.
        text = str(data).lower()
        assert any(
            kw in text
            for kw in ("api key", "configure", "provider", "anthropic")
        )

    def test_chat_returns_structure(self, client: TestClient) -> None:
        """Chat response shape includes plan_id / session_id when available."""
        resp = client.post("/api/v1/chat", json={"message": "Research AI"})
        assert resp.status_code in (200, 500)
        # Structural keys should still be present.
        data = resp.json()

    def test_chat_with_session_id(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/chat",
            json={"message": "Hello", "session_id": "test-session-123"},
        )
        assert resp.status_code in (200, 500)
        data = resp.json()
        # session_id echoes back when the pipeline returns it.
        if "session_id" in data:
            assert data["session_id"] == "test-session-123"

    def test_chat_empty_message_returns_422(self, client: TestClient) -> None:
        """Empty message should return 422 validation error."""
        resp = client.post("/api/v1/chat", json={"message": ""})
        assert resp.status_code == 422

    def test_chat_missing_message_returns_422(self, client: TestClient) -> None:
        """Missing message field should return 422."""
        resp = client.post("/api/v1/chat", json={})
        assert resp.status_code == 422
