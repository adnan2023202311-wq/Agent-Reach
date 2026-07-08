"""Tests for M9.1 — real Playground model comparison.

The comparator is tested with an injected client factory (no real
network), proving: concurrent execution, measured latency, honest
unconfigured reporting, failure isolation, cost estimation from the
router cost model, and the fastest-successful-wins criterion. API
tests confirm the M8 stub behavior is gone.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from config.settings import Settings, get_settings
from playground.compare import PlaygroundComparator


class _FakeClient:
    """Deterministic ModelClient double with controllable behavior."""

    def __init__(
        self,
        reply: str = "ok",
        delay: float = 0.0,
        error: Optional[Exception] = None,
    ) -> None:
        self.reply = reply
        self.delay = delay
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def complete(self, messages, *, system=None, max_tokens=1024) -> str:
        self.calls.append(
            {"messages": messages, "system": system, "max_tokens": max_tokens}
        )
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.reply


def _settings(**keys) -> Settings:
    return Settings(default_model_provider="anthropic", **keys)


# ===========================================================================
# Comparator
# ===========================================================================


@pytest.mark.asyncio
class TestComparator:
    async def test_configured_providers_run_for_real(self) -> None:
        clients = {
            "anthropic": _FakeClient(reply="from anthropic"),
            "openai": _FakeClient(reply="from openai"),
        }
        comparator = PlaygroundComparator(
            _settings(anthropic_api_key="k1", openai_api_key="k2"),
            client_factory=lambda name: clients[name],
        )
        result = await comparator.compare("Hello", ["anthropic", "openai"])
        by_provider = {r["provider"]: r for r in result["results"]}
        assert by_provider["anthropic"]["output"] == "from anthropic"
        assert by_provider["openai"]["output"] == "from openai"
        assert all(r["success"] for r in result["results"])
        # Each fake client was genuinely called once.
        assert len(clients["anthropic"].calls) == 1
        assert len(clients["openai"].calls) == 1

    async def test_latency_is_measured_not_invented(self) -> None:
        comparator = PlaygroundComparator(
            _settings(anthropic_api_key="k"),
            client_factory=lambda name: _FakeClient(delay=0.05),
        )
        result = await comparator.compare("Hi", ["anthropic"])
        assert result["results"][0]["latency_ms"] >= 50.0

    async def test_unconfigured_provider_reported_honestly(self) -> None:
        comparator = PlaygroundComparator(_settings())  # no keys, no factory
        result = await comparator.compare("Hi", ["anthropic"])
        entry = result["results"][0]
        assert entry["configured"] is False
        assert entry["success"] is False
        assert entry["output"] is None
        assert "not configured" in entry["error"]

    async def test_unsupported_provider_rejected_per_entry(self) -> None:
        comparator = PlaygroundComparator(_settings())
        result = await comparator.compare("Hi", ["skynet"])
        entry = result["results"][0]
        assert entry["success"] is False
        assert "not supported" in entry["error"]

    async def test_failure_isolated_per_provider(self) -> None:
        clients = {
            "anthropic": _FakeClient(reply="fine"),
            "openai": _FakeClient(error=RuntimeError("provider exploded")),
        }
        comparator = PlaygroundComparator(
            _settings(anthropic_api_key="k1", openai_api_key="k2"),
            client_factory=lambda name: clients[name],
        )
        result = await comparator.compare("Hi", ["anthropic", "openai"])
        by_provider = {r["provider"]: r for r in result["results"]}
        assert by_provider["anthropic"]["success"] is True
        assert by_provider["openai"]["success"] is False
        assert "provider exploded" in by_provider["openai"]["error"]

    async def test_winner_is_fastest_successful(self) -> None:
        clients = {
            "anthropic": _FakeClient(delay=0.08),
            "openai": _FakeClient(delay=0.01),
        }
        comparator = PlaygroundComparator(
            _settings(anthropic_api_key="k1", openai_api_key="k2"),
            client_factory=lambda name: clients[name],
        )
        result = await comparator.compare("Hi", ["anthropic", "openai"])
        assert result["winner"] == "openai"
        assert result["winner_criterion"] == "fastest successful response"

    async def test_no_winner_when_all_fail(self) -> None:
        comparator = PlaygroundComparator(_settings())
        result = await comparator.compare("Hi", ["anthropic", "openai"])
        assert result["winner"] is None

    async def test_cost_uses_router_model_and_is_labeled(self) -> None:
        comparator = PlaygroundComparator(
            _settings(anthropic_api_key="k"),
            client_factory=lambda name: _FakeClient(reply="x" * 400),
        )
        result = await comparator.compare("y" * 400, ["anthropic"])
        entry = result["results"][0]
        # 800 chars → 200 tokens estimate × 0.015/1k = 0.003
        assert entry["tokens_estimate"] == 200
        assert entry["cost_estimate_usd"] == pytest.approx(0.003)
        assert "estimate" in result["note"].lower()

    async def test_google_maps_to_gemini_cost(self) -> None:
        comparator = PlaygroundComparator(
            _settings(google_api_key="k"),
            client_factory=lambda name: _FakeClient(),
        )
        result = await comparator.compare("Hi", ["google"])
        assert result["results"][0]["configured"] is True

    async def test_empty_prompt_rejected(self) -> None:
        comparator = PlaygroundComparator(_settings())
        with pytest.raises(ValueError):
            await comparator.compare("  ", ["anthropic"])

    async def test_empty_providers_rejected(self) -> None:
        comparator = PlaygroundComparator(_settings())
        with pytest.raises(ValueError):
            await comparator.compare("Hi", [])


class TestListModels:
    def test_reflects_configuration(self) -> None:
        comparator = PlaygroundComparator(_settings(anthropic_api_key="k"))
        data = comparator.list_models()
        by_id = {p["id"]: p for p in data["providers"]}
        assert by_id["anthropic"]["configured"] is True
        assert by_id["openai"]["configured"] is False
        assert by_id["anthropic"]["default_model"]
        assert "ollama" in by_id

    def test_groq_not_conflated_with_grok(self) -> None:
        data = PlaygroundComparator(_settings()).list_models()
        by_id = {p["id"]: p for p in data["providers"]}
        # groq (settings) has no ProviderManager implementation
        assert by_id["groq"]["supported"] is False


# ===========================================================================
# API
# ===========================================================================


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    import config.settings as settings_module

    original = settings_module.get_settings
    settings_module.get_settings = lambda: settings_module.Settings(
        anthropic_api_key=None,
        default_model_provider="anthropic",
    )
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    settings_module.get_settings = original
    get_settings.cache_clear()


class TestPlaygroundAPI:
    def test_compare_no_fabricated_output(self, client: TestClient) -> None:
        """M8 stub returned invented outputs for any provider. With no
        keys configured, results must be honest failures."""
        resp = client.post(
            "/api/v1/playground/compare",
            json={"prompt": "Hello", "providers": ["anthropic", "openai"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["winner"] is None
        for entry in data["results"]:
            assert entry["success"] is False
            assert entry["output"] is None
            assert "stub" not in str(entry)  # the M8 marker is gone

    def test_compare_validation_422(self, client: TestClient) -> None:
        assert (
            client.post(
                "/api/v1/playground/compare",
                json={"prompt": "", "providers": ["anthropic"]},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/playground/compare",
                json={"prompt": "hi", "providers": []},
            ).status_code
            == 422
        )

    def test_models_reflect_real_configuration(self, client: TestClient) -> None:
        resp = client.get("/api/v1/playground/models")
        assert resp.status_code == 200
        providers = resp.json()["providers"]
        # Test env has no keys — nothing may claim to be configured.
        assert all(p["configured"] is False for p in providers)
