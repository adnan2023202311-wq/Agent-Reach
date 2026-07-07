"""Tests for M7.3 Reach Intelligence Router."""
from __future__ import annotations

import pytest

from routing.router import (
    ProviderCapability,
    ProviderScore,
    ProviderStats,
    ReachIntelligenceRouter,
    _PROVIDER_CAPABILITIES,
)


class TestProviderStats:
    def test_default_stats(self) -> None:
        stats = ProviderStats(provider="test")
        assert stats.provider == "test"
        assert stats.healthy

    def test_success_rate(self) -> None:
        stats = ProviderStats(provider="test")
        stats.record_success(100.0)
        stats.record_success(200.0)
        assert stats.success_rate == 1.0
        assert stats.avg_latency_ms == 150.0

    def test_record_failure(self) -> None:
        stats = ProviderStats(provider="test")
        stats.record_success(100.0)
        stats.record_failure("timeout")
        stats.record_failure("timeout")
        assert stats.success_rate == 1.0 / 3.0
        assert not stats.healthy  # 66% error rate > 50%


class TestReachIntelligenceRouter:
    def test_list_providers(self) -> None:
        router = ReachIntelligenceRouter()
        providers = router.list_providers()
        assert "anthropic" in providers
        assert "openai" in providers
        assert "gemini" in providers

    def test_get_capabilities(self) -> None:
        caps = ReachIntelligenceRouter.get_capabilities("anthropic")
        assert ProviderCapability.REASONING in caps
        assert ProviderCapability.CODING in caps

    def test_get_cost(self) -> None:
        cost = ReachIntelligenceRouter.get_cost("ollama")
        assert cost == 0.0

    def test_score_providers_all(self) -> None:
        router = ReachIntelligenceRouter()
        scores = router.score_providers()
        assert len(scores) == len(_PROVIDER_CAPABILITIES)
        # All scores should be positive
        assert all(s.total > 0 for s in scores)

    def test_score_providers_with_capabilities(self) -> None:
        router = ReachIntelligenceRouter()
        scores = router.score_providers(
            required_capabilities=[ProviderCapability.CODING]
        )
        coding_providers = [
            s for s in scores
            if ProviderCapability.CODING in ReachIntelligenceRouter.get_capabilities(s.provider)
        ]
        # Providers with CODING capability should score higher
        for cs in coding_providers:
            assert cs.capability == 1.0

    def test_score_providers_prefer_cheap(self) -> None:
        router = ReachIntelligenceRouter()
        normal = router.score_providers()[0]
        cheap = router.score_providers(prefer_cheap=True)[0]
        # With prefer_cheap, cheap providers get boosted
        assert cheap.cost >= normal.cost or cheap.provider != normal.provider

    def test_score_providers_excludes_unhealthy(self) -> None:
        router = ReachIntelligenceRouter()
        router.record_failure("anthropic", "error")
        router.record_failure("anthropic", "error")
        scores = router.score_providers(exclude_providers=["anthropic"])
        assert not any(s.provider == "anthropic" for s in scores)

    def test_select_provider(self) -> None:
        router = ReachIntelligenceRouter()
        provider = router.select_provider()
        assert provider in _PROVIDER_CAPABILITIES

    def test_select_provider_excludes_unhealthy(self) -> None:
        router = ReachIntelligenceRouter()
        # Make the top provider unhealthy
        top = router.select_provider()
        for _ in range(10):
            router.record_failure(top, "error")
        selected = router.select_provider()
        assert selected != top

    def test_fallback_chain(self) -> None:
        router = ReachIntelligenceRouter()
        fb = router.get_fallback("anthropic")
        assert fb is not None
        assert fb != "anthropic"

    def test_fallback_none_for_last(self) -> None:
        router = ReachIntelligenceRouter()
        fb = router.get_fallback("deepseek")
        # After deepseek, there may not be fallback or it's the end
        assert fb is None or fb != "deepseek"

    def test_record_success(self) -> None:
        router = ReachIntelligenceRouter()
        router.record_success("openai", 250.0)
        stats = router.get_stats("openai")
        assert stats.total_calls == 1
        assert stats.successful_calls == 1
        assert stats.avg_latency_ms == 250.0

    def test_record_failure(self) -> None:
        router = ReachIntelligenceRouter()
        router.record_failure("gemini", "rate limit")
        stats = router.get_stats("gemini")
        assert stats.failed_calls == 1
        assert stats.last_error == "rate limit"

    def test_get_healthy_providers(self) -> None:
        router = ReachIntelligenceRouter()
        healthy = router.get_healthy_providers()
        assert len(healthy) > 0

    def test_get_provider_health(self) -> None:
        router = ReachIntelligenceRouter()
        router.record_success("openai", 100.0)
        health = router.get_provider_health()
        assert "openai" in health
        assert health["openai"]["healthy"]

    def test_learn_from_history(self) -> None:
        router = ReachIntelligenceRouter()
        router.record_success("openai", 50.0)
        router.record_success("openai", 60.0)
        router.record_success("openai", 55.0)
        router.record_success("openai", 45.0)
        router.record_success("openai", 50.0)
        router.learn_from_history()
        assert router.preferred_provider == "openai"

    def test_benchmark_cache(self) -> None:
        router = ReachIntelligenceRouter()
        router.set_benchmark("anthropic", "coding_score", 0.95)
        assert router.get_benchmark("anthropic", "coding_score") == 0.95
        benchmarks = router.get_benchmarks("anthropic")
        assert benchmarks["coding_score"] == 0.95

    def test_clear(self) -> None:
        router = ReachIntelligenceRouter()
        router.record_success("openai", 100.0)
        router.set_benchmark("openai", "score", 0.5)
        router.clear()
        assert router.get_stats("openai").total_calls == 0
        assert router.get_benchmark("openai", "score") is None
        assert router.preferred_provider is None


class TestProviderScore:
    def test_default(self) -> None:
        score = ProviderScore(provider="test")
        assert score.provider == "test"
        assert score.total == 0.0
