"""Unit tests for MockModelClient."""

from __future__ import annotations

import pytest

from infrastructure.mock_model_client import MockModelClient


class TestMockModelClient:
    def test_init_default_model(self) -> None:
        client = MockModelClient()
        assert client._model == "mock-model"

    def test_init_custom_model(self) -> None:
        client = MockModelClient(model="custom-model")
        assert client._model == "custom-model"

    async def test_complete_echoes_user_message(self) -> None:
        client = MockModelClient()
        messages = [{"role": "user", "content": "Hello world"}]
        result = await client.complete(messages)
        assert "Hello world" in result
        assert "MockModelClient" in result

    async def test_complete_with_system(self) -> None:
        client = MockModelClient()
        messages = [{"role": "user", "content": "Test"}]
        result = await client.complete(messages, system="Be helpful")
        assert "Be helpful" in result

    async def test_complete_with_max_tokens(self) -> None:
        client = MockModelClient()
        messages = [{"role": "user", "content": "Test"}]
        result = await client.complete(messages, max_tokens=512)
        assert "512" in result

    async def test_complete_multi_turn(self) -> None:
        client = MockModelClient()
        messages = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Response"},
            {"role": "user", "content": "Second"},
        ]
        result = await client.complete(messages)
        # Should echo the last user message.
        assert "Second" in result

    async def test_complete_empty_messages(self) -> None:
        client = MockModelClient()
        result = await client.complete([])
        assert "MockModelClient" in result
