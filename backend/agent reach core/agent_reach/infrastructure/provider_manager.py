"""
Infrastructure layer: Provider Manager 2.0 (M6.3).

Layer: Adapters — implements domain.interfaces.ModelClient.

Manages multiple model providers through one interface. Required
providers: Anthropic, OpenAI, Gemini, OpenRouter, DeepSeek, Ollama.

The ProviderManager itself implements ModelClient, so it can be
dropped in place of any specific provider client — composition.py
depends on ModelClient, not on AnthropicModelClient, so swapping in
the manager requires no changes to the composition root.

Runtime provider switching is supported: ``set_provider()`` changes
the active provider for all subsequent ``complete()`` calls. Each
provider maintains its own model selection, so switching back and
forth between providers remembers the last model used with each.

Design notes
------------
- Provider-specific SDK imports are lazy: the ``anthropic`` package is
  only imported when an AnthropicModelClient is actually constructed,
  not at module import time. This keeps the provider manager importable
  in environments where only some SDKs are installed.
- The existing ``AnthropicModelClient`` is reused unchanged — this
  module adds the routing/switching layer on top, it does not replace
  the adapter.
- Provider configuration (API keys, base URLs, default models) is
  injected at construction time via a plain dict, so the manager has
  no reason to read the environment directly (Blueprint Section 23:
  Security — centralized secret handling). Callers get keys from
  Settings and pass them in.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from domain.exceptions import ConfigurationError, ModelProviderError
from domain.interfaces import ModelClient

logger = logging.getLogger(__name__)

# Default model per provider. Used when the caller does not specify
# a model for a provider. These are sensible defaults that can be
# overridden per-provider via the ``models`` config dict.
_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-4o",
    "gemini": "gemini-2.5-flash",
    "openrouter": "auto",
    "deepseek": "deepseek-chat",
    "ollama": "llama3.2",
}

# All provider identifiers the manager knows about. This is the
# canonical list — the spec names these six.
SUPPORTED_PROVIDERS: tuple[str, ...] = (
    "anthropic",
    "openai",
    "gemini",
    "openrouter",
    "deepseek",
    "ollama",
)


class ProviderManager(ModelClient):
    """Route model calls to one of several provider clients.

    Parameters
    ----------
    provider_keys:
        Mapping of provider name → API key. Only providers with a key
        (or a client implementation) can be activated.
    default_provider:
        Which provider to use initially. Must be a key in
        ``provider_keys`` or have a client implementation.
    models:
        Optional mapping of provider name → model name. Overrides the
        default model for each provider.
    base_urls:
        Optional mapping of provider name → base URL. Used by providers
        that support a custom endpoint (OpenRouter, Ollama, DeepSeek).
    """

    def __init__(
        self,
        provider_keys: dict[str, Optional[str]],
        default_provider: str = "anthropic",
        models: Optional[dict[str, str]] = None,
        base_urls: Optional[dict[str, str]] = None,
    ) -> None:
        self._provider_keys: dict[str, Optional[str]] = dict(provider_keys)
        self._models: dict[str, str] = dict(models or {})
        self._base_urls: dict[str, str] = dict(base_urls or {})
        self._clients: dict[str, ModelClient] = {}
        self._active_provider: str = default_provider

        if default_provider not in SUPPORTED_PROVIDERS:
            raise ConfigurationError(
                f"Unsupported default provider '{default_provider}'. "
                f"Supported: {list(SUPPORTED_PROVIDERS)}"
            )

    # ------------------------------------------------------------------
    # Provider access
    # ------------------------------------------------------------------

    @property
    def active_provider(self) -> str:
        """The currently active provider name."""
        return self._active_provider

    @property
    def active_model(self) -> str:
        """The model name for the currently active provider."""
        return self._resolve_model(self._active_provider)

    def set_provider(self, provider: str) -> None:
        """Switch the active provider at runtime.

        Raises
        ------
        ConfigurationError:
            If the provider is not supported.
        """
        if provider not in SUPPORTED_PROVIDERS:
            raise ConfigurationError(
                f"Unsupported provider '{provider}'. "
                f"Supported: {list(SUPPORTED_PROVIDERS)}"
            )
        self._active_provider = provider
        logger.info("Switched active provider to: %s", provider)

    def set_model(self, provider: str, model: str) -> None:
        """Set the model name for a specific provider.

        The model is remembered per provider, so switching back to a
        provider restores its last model.
        """
        self._models[provider] = model
        logger.info("Set model for %s: %s", provider, model)

    def get_model(self, provider: str) -> str:
        """Get the configured model name for a provider."""
        return self._resolve_model(provider)

    def list_providers(self) -> list[str]:
        """Return all supported provider names, sorted."""
        return sorted(SUPPORTED_PROVIDERS)

    def list_configured_providers(self) -> list[str]:
        """Return providers that have a client available (either an
        API key or a client implementation).
        """
        return sorted(
            p for p in SUPPORTED_PROVIDERS if self._is_configured(p)
        )

    def is_provider_ready(self, provider: str) -> bool:
        """Whether a provider has a working client available."""
        return self._is_configured(provider)

    def get_provider_status(self) -> dict[str, dict[str, Any]]:
        """Return a status dict for every supported provider.

        Each entry has: ``configured`` (bool), ``model`` (str),
        ``active`` (bool).
        """
        return {
            p: {
                "configured": self._is_configured(p),
                "model": self._resolve_model(p),
                "active": p == self._active_provider,
            }
            for p in SUPPORTED_PROVIDERS
        }

    # ------------------------------------------------------------------
    # ModelClient interface
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        """Send ``messages`` to the active provider and return the reply.

        Lazily constructs the provider client on first use.
        """
        client = self._get_or_create_client(self._active_provider)
        return await client.complete(
            messages,
            system=system,
            max_tokens=max_tokens,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _is_configured(self, provider: str) -> bool:
        """Whether a provider has a key or a client implementation.

        M9 fix: also checks the persisted ProviderConfigStore, so keys
        saved via the Settings UI after startup are visible without a
        restart. Env var (already in _provider_keys) takes precedence.
        """
        if provider in self._clients:
            return True
        # Check if we have a key for it (env var from construction time).
        if self._provider_keys.get(provider):
            return True
        # M9 fix: check the persisted store as a fallback.
        try:
            from infrastructure.provider_config_store import get_provider_config_store
            return bool(get_provider_config_store().get_api_key(provider))
        except Exception:  # noqa: BLE001
            return False

    def _resolve_model(self, provider: str) -> str:
        """Resolve the model name for a provider (explicit → default)."""
        return self._models.get(provider, _DEFAULT_MODELS.get(provider, ""))

    # M9 fix (v2.8): the runtime uses "gemini" but the config store and
    # env vars use "google". When looking up a key for "gemini", also
    # check "google" (and vice versa).
    _PROVIDER_ALIASES: dict[str, str] = {
        "google": "gemini",
        "gemini": "google",
    }

    def _get_or_create_client(self, provider: str) -> ModelClient:
        """Return the client for ``provider``, creating it if needed.

        M9 fix: if the provider wasn't configured at construction time
        (no env var), check the persisted ProviderConfigStore before
        giving up. This makes keys saved via the Settings UI immediately
        usable without restarting the backend.

        M9 fix (v2.8): also checks the provider alias (google↔gemini)
        so a key saved under "google" in the store is found when the
        runtime asks for "gemini".
        """
        if provider in self._clients:
            return self._clients[provider]

        # M9 fix: if we don't have a key from env vars, try the store.
        # Check both the runtime name and its alias (google↔gemini).
        if not self._provider_keys.get(provider):
            try:
                from infrastructure.provider_config_store import get_provider_config_store
                store = get_provider_config_store()
                # Try the runtime name first, then the alias.
                for name in (provider, self._PROVIDER_ALIASES.get(provider, "")):
                    if not name:
                        continue
                    store_key = store.get_api_key(name)
                    if store_key:
                        self._provider_keys[provider] = store_key
                        logger.info(
                            "ProviderManager: picked up key for %s from config store (stored as %s)",
                            provider, name,
                        )
                        break
                # Also pick up base_url and model from the store.
                for name in (provider, self._PROVIDER_ALIASES.get(provider, "")):
                    if not name:
                        continue
                    store_base = store.get_base_url(name)
                    if store_base and provider not in self._base_urls:
                        self._base_urls[provider] = store_base
                    store_model = store.get_default_model(name)
                    if store_model and provider not in self._models:
                        self._models[provider] = store_model
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ProviderManager: could not read config store for %s: %s",
                    provider, exc,
                )

        client = self._create_client(provider)
        self._clients[provider] = client
        return client

    def _create_client(self, provider: str) -> ModelClient:
        """Build a ModelClient for a specific provider.

        Each provider's SDK import is lazy — only triggered when the
        provider is first used. This keeps the manager importable even
        if some SDKs are not installed.
        """
        key = self._provider_keys.get(provider)
        model = self._resolve_model(provider)
        base_url = self._base_urls.get(provider)

        if provider == "anthropic":
            # Reuse the existing adapter — it already handles key
            # validation and error wrapping.
            from infrastructure.model_client import AnthropicModelClient

            if not key:
                raise ConfigurationError(
                    "Anthropic provider requires an API key — set "
                    "ANTHROPIC_API_KEY in the environment or .env file."
                )
            return AnthropicModelClient(api_key=key, model=model)

        if provider == "openai":
            return _create_openai_client(api_key=key, model=model, base_url=base_url)

        if provider == "gemini":
            return _create_gemini_client(api_key=key, model=model, base_url=base_url)

        if provider == "openrouter":
            return _create_openrouter_client(api_key=key, model=model, base_url=base_url)

        if provider == "deepseek":
            return _create_deepseek_client(api_key=key, model=model, base_url=base_url)

        if provider == "ollama":
            return _create_ollama_client(api_key=key, model=model, base_url=base_url)

        raise ConfigurationError(f"Unsupported provider: {provider}")


# ---------------------------------------------------------------------------
# Provider-specific client factories
#
# Each factory returns a ModelClient implementation. The SDK imports
# are lazy (inside the factory) so the provider manager module can be
# imported without all SDKs installed.
# ---------------------------------------------------------------------------


def _create_openai_client(
    api_key: Optional[str],
    model: str,
    base_url: Optional[str] = None,
) -> ModelClient:
    """Build an OpenAI-compatible client.

    OpenAI, OpenRouter, and DeepSeek all expose an OpenAI-compatible
    API, so they share a client implementation parameterized by base
    URL and model. Ollama also exposes an OpenAI-compatible endpoint.
    """
    try:
        import openai
    except ImportError as exc:
        raise ConfigurationError(
            "openai package is required for OpenAI-compatible providers. "
            "Install it with: pip install openai"
        ) from exc

    if not api_key:
        raise ConfigurationError(
            "OpenAI provider requires an API key — set "
            "OPENAI_API_KEY in the environment or .env file."
        )

    return _OpenAICompatibleClient(
        api_key=api_key,
        model=model,
        base_url=base_url,
        provider_name="openai",
    )


def _create_gemini_client(
    api_key: Optional[str],
    model: str,
    base_url: Optional[str] = None,
) -> ModelClient:
    """Build a Gemini client using the OpenAI-compatible endpoint.

    The google-genai SDK is the native option, but the OpenAI-compatible
    endpoint at ``generativelanguage.googleapis.com`` is available without
    an additional dependency. We use the shared OpenAI-compatible client
    with Gemini's specific base URL.
    """
    try:
        import openai
    except ImportError as exc:
        raise ConfigurationError(
            "openai package is required for Gemini (OpenAI-compatible "
            "endpoint). Install it with: pip install openai"
        ) from exc

    if not api_key:
        raise ConfigurationError(
            "Gemini provider requires an API key — set "
            "GOOGLE_API_KEY in the environment or .env file."
        )

    effective_base = base_url or "https://generativelanguage.googleapis.com/v1beta/openai/"
    return _OpenAICompatibleClient(
        api_key=api_key,
        model=model,
        base_url=effective_base,
        provider_name="gemini",
    )


def _create_openrouter_client(
    api_key: Optional[str],
    model: str,
    base_url: Optional[str] = None,
) -> ModelClient:
    """Build an OpenRouter client (OpenAI-compatible)."""
    try:
        import openai
    except ImportError as exc:
        raise ConfigurationError(
            "openai package is required for OpenRouter. "
            "Install it with: pip install openai"
        ) from exc

    if not api_key:
        raise ConfigurationError(
            "OpenRouter provider requires an API key — set "
            "OPENROUTER_API_KEY in the environment or .env file."
        )

    effective_base = base_url or "https://openrouter.ai/api/v1"
    return _OpenAICompatibleClient(
        api_key=api_key,
        model=model,
        base_url=effective_base,
        provider_name="openrouter",
    )


def _create_deepseek_client(
    api_key: Optional[str],
    model: str,
    base_url: Optional[str] = None,
) -> ModelClient:
    """Build a DeepSeek client (OpenAI-compatible)."""
    try:
        import openai
    except ImportError as exc:
        raise ConfigurationError(
            "openai package is required for DeepSeek. "
            "Install it with: pip install openai"
        ) from exc

    if not api_key:
        raise ConfigurationError(
            "DeepSeek provider requires an API key — set "
            "DEEPSEEK_API_KEY in the environment or .env file."
        )

    effective_base = base_url or "https://api.deepseek.com/v1"
    return _OpenAICompatibleClient(
        api_key=api_key,
        model=model,
        base_url=effective_base,
        provider_name="deepseek",
    )


def _create_ollama_client(
    api_key: Optional[str],
    model: str,
    base_url: Optional[str] = None,
) -> ModelClient:
    """Build an Ollama client (OpenAI-compatible, local)."""
    try:
        import openai
    except ImportError as exc:
        raise ConfigurationError(
            "openai package is required for Ollama. "
            "Install it with: pip install openai"
        ) from exc

    # Ollama does not require an API key — it runs locally. We accept
    # any key (or none) and use a placeholder if none is provided.
    effective_base = base_url or "http://localhost:11434/v1"
    return _OpenAICompatibleClient(
        api_key=api_key or "ollama-local",
        model=model,
        base_url=effective_base,
        provider_name="ollama",
    )


class _OpenAICompatibleClient(ModelClient):
    """Shared implementation for providers that expose an OpenAI-compatible API.

    Used by OpenAI, Gemini (via OpenAI-compatible endpoint), OpenRouter,
    DeepSeek, and Ollama.

    Parameters
    ----------
    api_key:
        API key for the provider.
    model:
        Model name to use.
    base_url:
        Base URL for the provider's API. If None, the default OpenAI
        endpoint is used.
    provider_name:
        Human-readable provider name for error messages.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        provider_name: str = "openai",
    ) -> None:
        import openai

        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._provider_name = provider_name

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        request_messages: list[dict[str, str]] = []
        if system:
            request_messages.append({"role": "system", "content": system})
        request_messages.extend(messages)

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=request_messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            raise ModelProviderError(
                provider=self._provider_name, original_error=exc
            ) from exc

        content = response.choices[0].message.content if response.choices else ""
        return content or ""
