"""Unit tests for ProviderManager (M6.3)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.exceptions import ConfigurationError, ModelProviderError
from domain.interfaces import ModelClient
from infrastructure.provider_manager import (
    SUPPORTED_PROVIDERS,
    ProviderManager,
)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_provider_is_anthropic(self) -> None:
        pm = ProviderManager(provider_keys={"anthropic": "key"})
        assert pm.active_provider == "anthropic"

    def test_custom_default_provider(self) -> None:
        pm = ProviderManager(
            provider_keys={"anthropic": "a", "openai": "o"},
            default_provider="openai",
        )
        assert pm.active_provider == "openai"

    def test_unsupported_default_provider_raises(self) -> None:
        with pytest.raises(ConfigurationError, match="Unsupported default provider"):
            ProviderManager(provider_keys={}, default_provider="bogus")

    def test_supported_providers_list(self) -> None:
        assert "anthropic" in SUPPORTED_PROVIDERS
        assert "openai" in SUPPORTED_PROVIDERS
        assert "gemini" in SUPPORTED_PROVIDERS
        assert "openrouter" in SUPPORTED_PROVIDERS
        assert "deepseek" in SUPPORTED_PROVIDERS
        assert "ollama" in SUPPORTED_PROVIDERS


# ---------------------------------------------------------------------------
# Provider switching
# ---------------------------------------------------------------------------


class TestProviderSwitching:
    def test_set_provider(self) -> None:
        pm = ProviderManager(
            provider_keys={"anthropic": "a", "openai": "o"},
        )
        pm.set_provider("openai")
        assert pm.active_provider == "openai"

    def test_set_provider_unsupported_raises(self) -> None:
        pm = ProviderManager(provider_keys={"anthropic": "a"})
        with pytest.raises(ConfigurationError, match="Unsupported provider"):
            pm.set_provider("bogus")

    def test_set_provider_remembers_model(self) -> None:
        pm = ProviderManager(
            provider_keys={"anthropic": "a", "openai": "o"},
            models={"anthropic": "claude-3", "openai": "gpt-4"},
        )
        pm.set_provider("openai")
        assert pm.active_model == "gpt-4"
        pm.set_provider("anthropic")
        assert pm.active_model == "claude-3"

    def test_set_model(self) -> None:
        pm = ProviderManager(provider_keys={"anthropic": "a"})
        pm.set_model("anthropic", "claude-3-opus")
        assert pm.get_model("anthropic") == "claude-3-opus"

    def test_set_model_persists_across_switches(self) -> None:
        pm = ProviderManager(
            provider_keys={"anthropic": "a", "openai": "o"},
        )
        pm.set_model("openai", "gpt-4-turbo")
        pm.set_provider("anthropic")
        pm.set_provider("openai")
        assert pm.get_model("openai") == "gpt-4-turbo"


# ---------------------------------------------------------------------------
# Status and listing
# ---------------------------------------------------------------------------


class TestStatus:
    def test_list_providers(self) -> None:
        pm = ProviderManager(provider_keys={})
        providers = pm.list_providers()
        assert providers == sorted(SUPPORTED_PROVIDERS)

    def test_list_configured_providers(self) -> None:
        pm = ProviderManager(
            provider_keys={"anthropic": "a", "openai": "o", "ollama": None},
        )
        # ollama has no key but is still "configured" because it can run
        # locally without a key — but our _is_configured only checks for
        # a key. So only anthropic and openai are configured.
        configured = pm.list_configured_providers()
        assert "anthropic" in configured
        assert "openai" in configured

    def test_is_provider_ready(self) -> None:
        pm = ProviderManager(provider_keys={"anthropic": "a"})
        assert pm.is_provider_ready("anthropic") is True
        assert pm.is_provider_ready("openai") is False

    def test_get_provider_status(self) -> None:
        pm = ProviderManager(
            provider_keys={"anthropic": "a"},
            default_provider="anthropic",
        )
        status = pm.get_provider_status()
        assert status["anthropic"]["configured"] is True
        assert status["anthropic"]["active"] is True
        assert status["openai"]["configured"] is False
        assert status["openai"]["active"] is False


# ---------------------------------------------------------------------------
# complete() — Anthropic path (reuses existing adapter)
# ---------------------------------------------------------------------------


class TestCompleteAnthropic:
    async def test_complete_uses_active_provider(self) -> None:
        pm = ProviderManager(provider_keys={"anthropic": "test-key"})
        # Mock the AnthropicModelClient to avoid real API calls.
        mock_client = MagicMock(spec=ModelClient)
        mock_client.complete = AsyncMock(return_value="hello from anthropic")
        pm._clients["anthropic"] = mock_client

        result = await pm.complete([{"role": "user", "content": "hi"}])
        assert result == "hello from anthropic"
        mock_client.complete.assert_awaited_once()

    async def test_complete_passes_system_and_max_tokens(self) -> None:
        pm = ProviderManager(provider_keys={"anthropic": "test-key"})
        mock_client = MagicMock(spec=ModelClient)
        mock_client.complete = AsyncMock(return_value="ok")
        pm._clients["anthropic"] = mock_client

        await pm.complete(
            [{"role": "user", "content": "hi"}],
            system="be helpful",
            max_tokens=512,
        )
        mock_client.complete.assert_awaited_once_with(
            [{"role": "user", "content": "hi"}],
            system="be helpful",
            max_tokens=512,
        )


# ---------------------------------------------------------------------------
# complete() — OpenAI-compatible path
# ---------------------------------------------------------------------------


class TestCompleteOpenAICompatible:
    def _make_mock_openai_client(self, reply: str = "openai reply") -> Any:
        """Build a mock openai.AsyncOpenAI instance."""
        mock_instance = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = reply
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_instance.chat.completions.create = AsyncMock(return_value=mock_response)
        return mock_instance

    async def test_complete_openai(self) -> None:
        pm = ProviderManager(
            provider_keys={"anthropic": "a", "openai": "test-key"},
            default_provider="openai",
        )
        mock_instance = self._make_mock_openai_client("gpt says hi")

        with patch(
            "openai.AsyncOpenAI", return_value=mock_instance
        ) as mock_cls:
            result = await pm.complete([{"role": "user", "content": "hi"}])

        assert result == "gpt says hi"
        mock_cls.assert_called_once_with(api_key="test-key", base_url=None)

    async def test_complete_openai_with_system(self) -> None:
        pm = ProviderManager(
            provider_keys={"openai": "test-key"},
            default_provider="openai",
        )
        mock_instance = self._make_mock_openai_client("ok")

        with patch("openai.AsyncOpenAI", return_value=mock_instance):
            await pm.complete(
                [{"role": "user", "content": "hi"}],
                system="be concise",
            )

        call_args = mock_instance.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "be concise"}
        assert messages[1] == {"role": "user", "content": "hi"}

    async def test_complete_openai_error_wrapped(self) -> None:
        pm = ProviderManager(
            provider_keys={"openai": "test-key"},
            default_provider="openai",
        )
        mock_instance = MagicMock()
        mock_instance.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("connection reset")
        )

        with patch("openai.AsyncOpenAI", return_value=mock_instance):
            with pytest.raises(ModelProviderError) as exc_info:
                await pm.complete([{"role": "user", "content": "hi"}])

        assert exc_info.value.provider == "openai"

    async def test_complete_openrouter(self) -> None:
        pm = ProviderManager(
            provider_keys={"openrouter": "test-key"},
            default_provider="openrouter",
        )
        mock_instance = self._make_mock_openai_client("or reply")

        with patch(
            "openai.AsyncOpenAI", return_value=mock_instance
        ) as mock_cls:
            result = await pm.complete([{"role": "user", "content": "hi"}])

        assert result == "or reply"
        # OpenRouter uses a custom base URL.
        call_kwargs = mock_cls.call_args.kwargs
        assert "openrouter.ai" in call_kwargs["base_url"]

    async def test_complete_ollama_no_key_ok(self) -> None:
        pm = ProviderManager(
            provider_keys={},
            default_provider="ollama",
        )
        mock_instance = self._make_mock_openai_client("llama reply")

        with patch(
            "openai.AsyncOpenAI", return_value=mock_instance
        ) as mock_cls:
            result = await pm.complete([{"role": "user", "content": "hi"}])

        assert result == "llama reply"
        # Ollama uses localhost base URL and a placeholder key.
        call_kwargs = mock_cls.call_args.kwargs
        assert "localhost:11434" in call_kwargs["base_url"]
        assert call_kwargs["api_key"] == "ollama-local"


# ---------------------------------------------------------------------------
# Lazy client creation
# ---------------------------------------------------------------------------


class TestLazyCreation:
    def test_client_created_on_demand(self) -> None:
        pm = ProviderManager(provider_keys={"anthropic": "test-key"})
        assert "anthropic" not in pm._clients
        # The client is created lazily on first complete() — we don't
        # trigger that here, we just verify the dict starts empty.
        assert pm._clients == {}

    def test_client_reused_after_creation(self) -> None:
        pm = ProviderManager(provider_keys={"anthropic": "test-key"})
        mock_client = MagicMock(spec=ModelClient)
        pm._clients["anthropic"] = mock_client
        # After manually injecting, _get_or_create_client returns it.
        result = pm._get_or_create_client("anthropic")
        assert result is mock_client
