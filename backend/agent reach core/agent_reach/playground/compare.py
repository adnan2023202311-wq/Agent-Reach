"""
Playground model comparison (M9.1 — replaces the M8 stub).

Layer: Application — composes the existing ProviderManager and
ReachIntelligenceRouter cost model. No parallel provider stack.

The M8 /playground/compare endpoint fabricated outputs, latencies,
costs, and quality scores. This service executes REAL provider calls:

- Configured providers run concurrently through ModelClients built by
  the existing ProviderManager factories; latency is measured, not
  invented.
- Unconfigured providers are reported honestly as `configured: false`
  with no fabricated output.
- Cost is estimated from the router's per-provider cost model and the
  actual prompt/response sizes, and labeled an estimate.
- The "winner" is the fastest successful response — an honest,
  measurable criterion (no invented quality score).

Token counts use the chars/4 heuristic already used across the
codebase (memory context windows); they are labeled estimates.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from config.settings import KNOWN_PROVIDERS, Settings
from infrastructure.provider_manager import (
    SUPPORTED_PROVIDERS,
    ProviderManager,
    _DEFAULT_MODELS,
)

# Settings uses "google"; ProviderManager/router use "gemini".
_SETTINGS_TO_MANAGER: dict[str, str] = {"google": "gemini"}

_CHARS_PER_TOKEN = 4.0


@dataclass
class CompareEntry:
    """Result of one provider's real execution (or honest absence)."""

    provider: str
    configured: bool
    model: str = ""
    output: Optional[str] = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    tokens_estimate: int = 0
    cost_estimate_usd: float = 0.0
    success: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "model": self.model,
            "output": self.output,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "tokens_estimate": self.tokens_estimate,
            "cost_estimate_usd": self.cost_estimate_usd,
            "success": self.success,
        }


class PlaygroundComparator:
    """Run one prompt against several providers, for real.

    Parameters
    ----------
    settings:
        Source of provider API keys.
    client_factory:
        Optional override returning a ModelClient for a manager-name
        provider — injected by tests to avoid real network calls.
        Production uses the ProviderManager's own factories.
    timeout_seconds:
        Per-provider timeout for the comparison call.
    """

    def __init__(
        self,
        settings: Settings,
        client_factory: Optional[Any] = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._settings = settings
        self._client_factory = client_factory
        self._timeout = timeout_seconds

    # ── Public API ──────────────────────────────────────────────

    def list_models(self) -> dict[str, Any]:
        """Real provider/model availability from configuration.

        Models come from the ProviderManager's default-model mapping;
        `configured` reflects whether a key is actually present.
        """
        providers = []
        for provider_id in KNOWN_PROVIDERS:
            manager_name = _SETTINGS_TO_MANAGER.get(provider_id, provider_id)
            supported = manager_name in SUPPORTED_PROVIDERS
            providers.append(
                {
                    "id": provider_id,
                    "configured": bool(self._settings.provider_api_key(provider_id)),
                    "supported": supported,
                    "default_model": _DEFAULT_MODELS.get(manager_name, ""),
                }
            )
        # ollama needs no key — supported but reported unconfigured
        # unless a base URL/environment makes it reachable; we don't
        # probe the network here.
        providers.append(
            {
                "id": "ollama",
                "configured": False,
                "supported": True,
                "default_model": _DEFAULT_MODELS.get("ollama", ""),
            }
        )
        return {"providers": providers}

    async def compare(
        self,
        prompt: str,
        providers: list[str],
        max_tokens: int = 512,
        system: str = "",
    ) -> dict[str, Any]:
        """Execute `prompt` against each provider concurrently."""
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        if not providers:
            raise ValueError("at least one provider is required")

        entries = await asyncio.gather(
            *(
                self._run_one(provider, prompt, max_tokens, system)
                for provider in providers
            )
        )

        successful = [e for e in entries if e.success]
        winner = (
            min(successful, key=lambda e: e.latency_ms).provider
            if successful
            else None
        )
        return {
            "prompt": prompt,
            "results": [e.to_dict() for e in entries],
            "winner": winner,
            "winner_criterion": "fastest successful response",
            "note": "Token and cost values are estimates (chars/4 heuristic × router cost model).",
        }

    # ── Internals ───────────────────────────────────────────────

    async def _run_one(
        self, provider: str, prompt: str, max_tokens: int, system: str
    ) -> CompareEntry:
        manager_name = _SETTINGS_TO_MANAGER.get(provider, provider)
        entry = CompareEntry(
            provider=provider,
            configured=False,
            model=_DEFAULT_MODELS.get(manager_name, ""),
        )

        if manager_name not in SUPPORTED_PROVIDERS:
            entry.error = f"Provider '{provider}' is not supported"
            return entry

        api_key = self._settings.provider_api_key(provider)
        if not api_key and self._client_factory is None:
            entry.error = (
                f"Provider '{provider}' is not configured — no API key present"
            )
            return entry

        entry.configured = True
        start = time.perf_counter()
        try:
            client = self._build_client(manager_name, api_key)
            output = await asyncio.wait_for(
                client.complete(
                    [{"role": "user", "content": prompt}],
                    system=system or None,
                    max_tokens=max_tokens,
                ),
                timeout=self._timeout,
            )
            entry.output = output
            entry.success = True
        except asyncio.TimeoutError:
            entry.error = f"Timed out after {self._timeout}s"
        except Exception as exc:  # noqa: BLE001 — isolation boundary
            entry.error = f"{type(exc).__name__}: {exc}"
        entry.latency_ms = (time.perf_counter() - start) * 1000

        chars = len(prompt) + len(entry.output or "")
        entry.tokens_estimate = int(chars / _CHARS_PER_TOKEN)
        entry.cost_estimate_usd = self._estimate_cost(
            manager_name, entry.tokens_estimate
        )
        return entry

    def _build_client(self, manager_name: str, api_key: Optional[str]) -> Any:
        if self._client_factory is not None:
            return self._client_factory(manager_name)
        # Reuse the ProviderManager's client factories — one manager
        # per call keeps provider selection explicit and stateless.
        manager = ProviderManager(
            provider_keys={manager_name: api_key},
            default_provider=manager_name,
        )
        return manager._get_or_create_client(manager_name)

    @staticmethod
    def _estimate_cost(manager_name: str, tokens: int) -> float:
        from routing.router import ReachIntelligenceRouter

        per_1k = ReachIntelligenceRouter.get_cost(manager_name)
        return round(per_1k * tokens / 1000.0, 8)
