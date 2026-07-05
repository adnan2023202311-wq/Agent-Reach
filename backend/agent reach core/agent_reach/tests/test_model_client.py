"""
Unit tests for AnthropicModelClient, fully mocked — no network access
and no real API key required. These verify two things only this
adapter is responsible for: refusing to construct without a key, and
translating provider failures into ModelProviderError.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from domain.exceptions import ConfigurationError, ModelProviderError
from infrastructure.model_client import AnthropicModelClient


def test_missing_api_key_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        AnthropicModelClient(api_key=None, model="claude-sonnet-4-6")


async def test_complete_returns_concatenated_text_blocks() -> None:
    client = AnthropicModelClient(api_key="fake-key", model="claude-sonnet-4-6")

    text_block = type("Block", (), {"type": "text", "text": "hello "})()
    other_block = type("Block", (), {"type": "tool_use", "text": "ignored"})()
    another_text_block = type("Block", (), {"type": "text", "text": "world"})()
    fake_response = type(
        "Response", (), {"content": [text_block, other_block, another_text_block]}
    )()
    client._client.messages.create = AsyncMock(return_value=fake_response)

    result = await client.complete([{"role": "user", "content": "hi"}])

    assert result == "hello world"


async def test_provider_failure_is_wrapped_as_model_provider_error() -> None:
    client = AnthropicModelClient(api_key="fake-key", model="claude-sonnet-4-6")
    client._client.messages.create = AsyncMock(side_effect=RuntimeError("connection reset"))

    with pytest.raises(ModelProviderError) as exc_info:
        await client.complete([{"role": "user", "content": "hi"}])

    assert exc_info.value.provider == "anthropic"
