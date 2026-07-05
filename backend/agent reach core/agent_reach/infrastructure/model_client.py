"""
Infrastructure layer: AnthropicModelClient.

Layer: Adapters — implements domain.interfaces.ModelClient.

This is the ONLY file in the codebase allowed to import the
`anthropic` package. Every other module that needs to call a model
depends on domain.interfaces.ModelClient instead — the same rule
already applied to Agent implementations vs. AgentDispatcher.

Not yet wired into any Agent (see composition.py and
docs/ARCHITECTURE.md) — building the adapter and connecting it to a
real agent are treated as two separate, separately-verifiable steps.
"""

from __future__ import annotations

from typing import Any, Optional

import anthropic

from domain.exceptions import ConfigurationError, ModelProviderError
from domain.interfaces import ModelClient


class AnthropicModelClient(ModelClient):
    def __init__(self, api_key: Optional[str], model: str) -> None:
        if not api_key:
            raise ConfigurationError(
                "AnthropicModelClient requires an API key — set "
                "ANTHROPIC_API_KEY in the environment or .env file."
            )
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        request_kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            request_kwargs["system"] = system

        try:
            response = await self._client.messages.create(**request_kwargs)
        except Exception as exc:  # noqa: BLE001 - isolate callers from SDK-specific
            # exception types entirely, same reasoning as AgentDispatcher's
            # centralized error handling.
            raise ModelProviderError(provider="anthropic", original_error=exc) from exc

        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
