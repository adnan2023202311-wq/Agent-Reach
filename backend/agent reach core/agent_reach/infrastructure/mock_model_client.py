"""
Infrastructure layer: MockModelClient.

Layer: Adapters — implements domain.interfaces.ModelClient.

A mock model client that returns canned responses without making any
network calls. Used as a fallback when no real provider credentials are
available (development mode, testing, demos).

This preserves the Alpha Validation behavior where the platform could
boot without real provider credentials. The mock client returns a
deterministic echo response that includes the input, so tests and
demos can verify the full pipeline works end-to-end.

Design notes
------------
- The mock client does NOT import any provider SDK. It is always
  available, regardless of which packages are installed.
- Responses are deterministic: they echo the last user message.
- The mock is explicitly a development/testing tool — it is never
  selected when real credentials exist.
"""

from __future__ import annotations

import logging
from typing import Optional

from domain.interfaces import ModelClient

logger = logging.getLogger(__name__)


class MockModelClient(ModelClient):
    """A mock model client that returns canned responses.

    Used as a fallback when no real provider credentials are available.
    Returns a deterministic echo response that includes the input.
    """

    def __init__(self, model: str = "mock-model") -> None:
        self._model = model
        logger.info("Initialized MockModelClient (model=%s)", model)

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:
        """Return a mock response that echoes the last user message."""
        # Find the last user message.
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = msg.get("content", "")
                break

        return (
            f"[MockModelClient] Echo: {last_user!r} "
            f"(system={system!r}, max_tokens={max_tokens})"
        )
