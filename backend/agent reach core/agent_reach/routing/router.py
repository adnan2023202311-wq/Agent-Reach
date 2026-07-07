"""
Reach Intelligence Router (M7.3).

Dynamic model routing with intelligent provider selection.
Never ties Agent-Reach to a single provider. Every provider is a capability.

Features:
- Dynamic Provider Selection
- Capability/Latency/Cost/Context/Reliability Scoring
- Automatic Fallback
- Provider Health Monitoring
- Provider Benchmark Cache
- Provider Learning

Layer: Application/Core — depends inward on domain/ and infrastructure/ only.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ProviderCapability(str, Enum):
    """Known provider capabilities used for scoring."""
    REASONING = "reasoning"
    CODING = "coding"
    FAST = "fast"
    CHEAP = "cheap"
    LONG_CONTEXT = "long_context"
    MULTIMODAL = "multimodal"
    TOOL_USE = "tool_use"


# Canonical capability sets per provider
_PROVIDER_CAPABILITIES: dict[str, set[ProviderCapability]] = {
    "anthropic": {
        ProviderCapability.REASONING,
        ProviderCapability.CODING,
        ProviderCapability.LONG_CONTEXT,
        ProviderCapability.TOOL_USE,
    },
    "openai": {
        ProviderCapability.REASONING,
        ProviderCapability.CODING,
        ProviderCapability.FAST,
        ProviderCapability.MULTIMODAL,
        ProviderCapability.TOOL_USE,
    },
    "gemini": {
        ProviderCapability.FAST,
        ProviderCapability.CHEAP,
        ProviderCapability.LONG_CONTEXT,
        ProviderCapability.MULTIMODAL,
    },
    "openrouter": {
        ProviderCapability.REASONING,
        ProviderCapability.CODING,
        ProviderCapability.CHEAP,
    },
    "deepseek": {
        ProviderCapability.REASONING,
        ProviderCapability.CODING,
        ProviderCapability.CHEAP,
    },
    "ollama": {
        ProviderCapability.CHEAP,
        ProviderCapability.FAST,
    },
    "grok": {
        ProviderCapability.REASONING,
        ProviderCapability.FAST,
        ProviderCapability.LONG_CONTEXT,
    },
}


# Relative cost per 1K tokens (rough estimates for comparison)
_PROVIDER_COSTS: dict[str, float] = {
    "anthropic": 0.015,
    "openai": 0.010,
    "gemini": 0.005,
    "openrouter": 0.008,
    "deepseek": 0.002,
    "ollama": 0.0,
    "grok": 0.008,
}


@dataclass
class ProviderScore:
    """Computed score for a provider."""

    provider: str
    total: float = 0.0
    capability: float = 0.0
    latency: float = 0.0
    cost: float = 0.0
    context_size: float = 0.0
    reliability: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderStats:
    """Runtime statistics for a provider."""

    provider: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    last_call_time: float = 0.0
    last_error: str = ""
    healthy: bool = True

    @property
    def success_rate(self) -> float:
        return self.successful_calls / max(1, self.total_calls)

    @property
    def error_rate(self) -> float:
        return self.failed_calls / max(1, self.total_calls)

    def record_success(self, latency_ms: float) -> None:
        self.total_calls += 1
        self.successful_calls += 1
        self.total_latency_ms += latency_ms
        self.avg_latency_ms = self.total_latency_ms / self.total_calls
        self.last_call_time = time.time()
        self.healthy = True

    def record_failure(self, error: str) -> None:
        self.total_calls += 1
        self.failed_calls += 1
        self.last_error = error
        self.last_call_time = time.time()
        if self.error_rate > 0.5:
            self.healthy = False


class ReachIntelligenceRouter:
    """Intelligent provider router with multi-dimensional scoring.

    Routes requests to the best provider based on:
    - Required capabilities
    - Historical latency
    - Cost sensitivity
    - Context size requirements
    - Reliability history
    - Automatic fallback when primary fails
    """

    def __init__(
        self,
        capability_weight: float = 0.30,
        latency_weight: float = 0.25,
        cost_weight: float = 0.20,
        context_weight: float = 0.15,
        reliability_weight: float = 0.10,
        fallback_chain: Optional[list[str]] = None,
    ) -> None:
        self._capability_weight = capability_weight
        self._latency_weight = latency_weight
        self._cost_weight = cost_weight
        self._context_weight = context_weight
        self._reliability_weight = reliability_weight
        self._fallback_chain = fallback_chain or [
            "anthropic", "openai", "gemini", "openrouter", "deepseek"
        ]
        self._stats: dict[str, ProviderStats] = {}
        self._benchmark_cache: dict[str, dict[str, float]] = {}
        self._preferred_provider: Optional[str] = None

    # ------------------------------------------------------------------
    # Provider scoring
    # ------------------------------------------------------------------

    def score_providers(
        self,
        required_capabilities: Optional[list[ProviderCapability]] = None,
        prefer_cheap: bool = False,
        context_size: int = 0,
        exclude_providers: Optional[list[str]] = None,
    ) -> list[ProviderScore]:
        """Score all known providers for a given request.

        Args:
            required_capabilities: Capabilities needed for this request.
            prefer_cheap: Weight cost more heavily.
            context_size: Estimated context size (longer context favors
                providers with large context windows).
            exclude_providers: Providers to exclude (e.g., unhealthy).

        Returns:
            List of ProviderScores sorted by total descending.
        """
        required = set(required_capabilities or [])
        excluded = set(exclude_providers or [])

        # Adjust weights if cost-sensitive
        cap_w = self._capability_weight
        cost_w = self._cost_weight * (2.0 if prefer_cheap else 1.0)

        scores: list[ProviderScore] = []
        for provider in _PROVIDER_CAPABILITIES:
            if provider in excluded:
                continue

            capabilities = _PROVIDER_CAPABILITIES.get(provider, set())

            # Capability score: how many required capabilities match
            if required:
                matches = len(required & capabilities)
                capability_score = matches / len(required)
            else:
                capability_score = 1.0

            # Latency score: inverse of average latency (normalized)
            stats = self._stats.get(provider)
            if stats and stats.avg_latency_ms > 0:
                # Lower latency = higher score
                latency_score = 1.0 / (1.0 + stats.avg_latency_ms / 1000.0)
            else:
                latency_score = 0.5  # Neutral for unknown

            # Cost score: cheaper = higher score
            cost = _PROVIDER_COSTS.get(provider, 0.01)
            cost_score = 1.0 / (1.0 + cost * 100.0)

            # Context size score
            if context_size > 0:
                has_long_context = ProviderCapability.LONG_CONTEXT in capabilities
                context_score = 1.0 if has_long_context else 0.5
            else:
                context_score = 0.5

            # Reliability score
            if stats:
                reliability_score = stats.success_rate
            else:
                reliability_score = 0.8  # Assume reliable until proven otherwise

            total = (
                cap_w * capability_score
                + self._latency_weight * latency_score
                + cost_w * cost_score
                + self._context_weight * context_score
                + self._reliability_weight * reliability_score
            )

            scores.append(
                ProviderScore(
                    provider=provider,
                    total=total,
                    capability=capability_score,
                    latency=latency_score,
                    cost=cost_score,
                    context_size=context_score,
                    reliability=reliability_score,
                )
            )

        scores.sort(key=lambda s: s.total, reverse=True)
        return scores

    def select_provider(
        self,
        required_capabilities: Optional[list[ProviderCapability]] = None,
        prefer_cheap: bool = False,
        context_size: int = 0,
    ) -> str:
        """Select the best provider for a request.

        Automatically excludes unhealthy providers.
        """
        unhealthy = {
            p for p, s in self._stats.items() if not s.healthy
        }
        scores = self.score_providers(
            required_capabilities=required_capabilities,
            prefer_cheap=prefer_cheap,
            context_size=context_size,
            exclude_providers=list(unhealthy),
        )
        if not scores:
            return self._fallback_chain[0]
        return scores[0].provider

    def get_fallback(self, failed_provider: str) -> Optional[str]:
        """Get the next fallback provider after a failure."""
        try:
            idx = self._fallback_chain.index(failed_provider)
            for next_provider in self._fallback_chain[idx + 1:]:
                stats = self._stats.get(next_provider)
                if stats is None or stats.healthy:
                    return next_provider
        except ValueError:
            pass
        return None

    # ------------------------------------------------------------------
    # Stats & Health
    # ------------------------------------------------------------------

    def get_stats(self, provider: str) -> ProviderStats:
        """Get or create provider statistics."""
        if provider not in self._stats:
            self._stats[provider] = ProviderStats(provider=provider)
        return self._stats[provider]

    def record_success(self, provider: str, latency_ms: float) -> None:
        """Record a successful provider call."""
        stats = self.get_stats(provider)
        stats.record_success(latency_ms)

    def record_failure(self, provider: str, error: str) -> None:
        """Record a failed provider call."""
        stats = self.get_stats(provider)
        stats.record_failure(error)

    def get_healthy_providers(self) -> list[str]:
        """Return all currently healthy providers."""
        healthy: list[str] = []
        for provider, stats in self._stats.items():
            if stats.healthy:
                healthy.append(provider)
        for provider in _PROVIDER_CAPABILITIES:
            if provider not in self._stats:
                healthy.append(provider)
        return healthy

    def get_provider_health(self) -> dict[str, dict[str, Any]]:
        """Get health status for all providers."""
        result: dict[str, dict[str, Any]] = {}
        for provider in _PROVIDER_CAPABILITIES:
            stats = self._stats.get(provider)
            if stats:
                result[provider] = {
                    "healthy": stats.healthy,
                    "success_rate": stats.success_rate,
                    "avg_latency_ms": stats.avg_latency_ms,
                    "total_calls": stats.total_calls,
                    "last_error": stats.last_error,
                }
            else:
                result[provider] = {
                    "healthy": True,
                    "success_rate": 1.0,
                    "avg_latency_ms": 0,
                    "total_calls": 0,
                    "last_error": "",
                }
        return result

    # ------------------------------------------------------------------
    # Provider Learning
    # ------------------------------------------------------------------

    @property
    def preferred_provider(self) -> Optional[str]:
        """The currently preferred provider based on learning."""
        return self._preferred_provider

    def learn_from_history(self) -> None:
        """Analyze provider history and update preferences.

        The provider with the best combination of success rate and
        latency becomes the preferred provider.
        """
        best_score = -1.0
        best_provider: Optional[str] = None

        for provider, stats in self._stats.items():
            if not stats.healthy or stats.total_calls < 5:
                continue
            # Composite: success_rate weighted more than speed
            score = (
                stats.success_rate * 0.7
                + (1.0 / (1.0 + stats.avg_latency_ms / 1000.0)) * 0.3
            )
            if score > best_score:
                best_score = score
                best_provider = provider

        self._preferred_provider = best_provider

    # ------------------------------------------------------------------
    # Benchmark Cache
    # ------------------------------------------------------------------

    def set_benchmark(self, provider: str, metric: str, value: float) -> None:
        """Store a benchmark value for a provider."""
        self._benchmark_cache.setdefault(provider, {})[metric] = value

    def get_benchmark(self, provider: str, metric: str) -> Optional[float]:
        """Retrieve a cached benchmark value."""
        return self._benchmark_cache.get(provider, {}).get(metric)

    def get_benchmarks(self, provider: str) -> dict[str, float]:
        """Get all cached benchmarks for a provider."""
        return dict(self._benchmark_cache.get(provider, {}))

    # ------------------------------------------------------------------
    # Capability queries
    # ------------------------------------------------------------------

    @staticmethod
    def get_capabilities(provider: str) -> set[ProviderCapability]:
        """Get the capabilities of a provider."""
        return _PROVIDER_CAPABILITIES.get(provider, set())

    @staticmethod
    def get_cost(provider: str) -> float:
        """Get the relative cost of a provider."""
        return _PROVIDER_COSTS.get(provider, 0.01)

    @staticmethod
    def list_providers() -> list[str]:
        """List all known providers."""
        return list(_PROVIDER_CAPABILITIES.keys())

    def clear(self) -> None:
        """Reset all stats and cache."""
        self._stats.clear()
        self._benchmark_cache.clear()
        self._preferred_provider = None
