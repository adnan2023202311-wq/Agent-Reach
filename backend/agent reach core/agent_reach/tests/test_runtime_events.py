"""Tests for M9.24 — Event-Driven runtime.

Covers the RuntimeEventHub (composition around the EXISTING M2
EventBus — subscribers on the underlying bus still fire), pipeline
event publishing (canonical chain, request_id joinable to the
persisted trace, isolation from request processing), and the
/api/v1/events endpoints.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from composition import build_event_hub, build_intelligent_pipeline
from config.settings import get_settings
from core.runtime_events import RuntimeEvent, RuntimeEventHub


# ===========================================================================
# Hub
# ===========================================================================


@pytest.mark.asyncio
class TestRuntimeEventHub:
    async def test_publish_records_and_fans_out(self) -> None:
        hub = RuntimeEventHub()
        received: list[tuple[str, dict[str, Any]]] = []

        async def handler(event_type: str, payload: dict[str, Any]) -> None:
            received.append((event_type, payload))

        hub.subscribe("test.event", handler)
        record = await hub.publish("test.event", {"a": 1})
        assert record.event_id
        assert received == [("test.event", {"a": 1})]
        assert len(hub.get_events()) == 1

    async def test_underlying_bus_subscribers_still_fire(self) -> None:
        """Plugins subscribing directly on the EXISTING EventBus keep
        working — the hub composes, it does not replace."""
        hub = RuntimeEventHub()
        seen: list[str] = []

        async def plugin_handler(event_type: str, payload: dict[str, Any]) -> None:
            seen.append(event_type)

        hub.bus.subscribe("direct.event", plugin_handler)
        await hub.publish("direct.event", {})
        assert seen == ["direct.event"]

    async def test_failing_subscriber_does_not_break_publish(self) -> None:
        hub = RuntimeEventHub()

        async def broken(event_type: str, payload: dict[str, Any]) -> None:
            raise RuntimeError("subscriber exploded")

        hub.subscribe("x", broken)
        record = await hub.publish("x", {})  # must not raise
        assert record.event_type == "x"

    async def test_event_log_filters(self) -> None:
        hub = RuntimeEventHub()
        await hub.publish("alpha", {})
        first_ts = hub.get_events()[0].timestamp
        await hub.publish("beta", {})
        await hub.publish("alpha", {})

        assert len(hub.get_events(event_type="alpha")) == 2
        assert len(hub.get_events(event_type="beta")) == 1
        # newest first
        assert hub.get_events()[0].event_type == "alpha"
        # since filter excludes the first event
        newer = hub.get_events(since=first_ts)
        assert all(e.timestamp > first_ts for e in newer)

    async def test_log_bounded(self) -> None:
        hub = RuntimeEventHub(max_log=3)
        for i in range(6):
            await hub.publish(f"e{i}", {})
        assert len(hub.get_events(limit=100)) == 3
        assert hub.get_stats()["total_events"] == 3

    async def test_stats_count_by_type(self) -> None:
        hub = RuntimeEventHub()
        await hub.publish("a", {})
        await hub.publish("a", {})
        await hub.publish("b", {})
        stats = hub.get_stats()
        assert stats["by_type"] == {"a": 2, "b": 1}
        assert RuntimeEvent.PIPELINE_COMPLETED in stats["known_types"]

    async def test_invalid_max_log_rejected(self) -> None:
        with pytest.raises(ValueError):
            RuntimeEventHub(max_log=0)


# ===========================================================================
# Pipeline integration
# ===========================================================================


@pytest.mark.asyncio
class TestPipelineEventPublishing:
    async def test_execution_publishes_canonical_chain(self) -> None:
        hub = build_event_hub()
        pipeline = build_intelligent_pipeline(event_hub=hub)
        result = await pipeline.process("Research event-driven systems")

        types = [e.event_type for e in hub.get_events(limit=100)]
        assert RuntimeEvent.PIPELINE_STARTED in types
        assert RuntimeEvent.MEMORY_UPDATED in types
        assert RuntimeEvent.KNOWLEDGE_UPDATED in types
        assert RuntimeEvent.REFLECTION_TRIGGERED in types
        assert RuntimeEvent.LEARNING_TRIGGERED in types
        assert RuntimeEvent.PIPELINE_COMPLETED in types

        # Every event joins back to the persisted trace.
        request_id = result.trace.request_id
        for event in hub.get_events(limit=100):
            assert event.payload["request_id"] == request_id
        assert pipeline.get_trace(request_id) is not None

    async def test_no_hub_means_no_publishing(self) -> None:
        """Backward compatibility: pipelines without a hub behave
        exactly as before."""
        pipeline = build_intelligent_pipeline()  # no hub
        result = await pipeline.process("silent run")
        assert result.outcome is not None  # simply no error

    async def test_broken_hub_never_breaks_requests(self) -> None:
        class _ExplodingHub:
            async def publish(self, *a: Any, **k: Any) -> None:
                raise RuntimeError("hub down")

        pipeline = build_intelligent_pipeline(event_hub=_ExplodingHub())
        result = await pipeline.process("resilient run")
        assert result.outcome.status.value == "succeeded"


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


class TestEventsAPI:
    def test_empty_on_boot(self, client: TestClient) -> None:
        data = client.get("/api/v1/events").json()
        assert data["count"] == 0

    def test_chat_produces_real_events(self, client: TestClient) -> None:
        chat = client.post("/api/v1/chat", json={"message": "Emit events"}).json()
        data = client.get("/api/v1/events?limit=100").json()
        assert data["count"] >= 4
        types = {e["event_type"] for e in data["events"]}
        assert "pipeline.completed" in types
        # Events join to the chat's persisted trace.
        assert any(
            e["payload"].get("request_id") == chat["request_id"]
            for e in data["events"]
        )

    def test_type_filter(self, client: TestClient) -> None:
        client.post("/api/v1/chat", json={"message": "More events"})
        data = client.get("/api/v1/events?event_type=pipeline.completed").json()
        assert data["count"] >= 1
        assert all(
            e["event_type"] == "pipeline.completed" for e in data["events"]
        )

    def test_stats_endpoint(self, client: TestClient) -> None:
        client.post("/api/v1/chat", json={"message": "Stat me"})
        stats = client.get("/api/v1/events/stats").json()
        assert stats["total_events"] >= 1
        assert "pipeline.completed" in stats["by_type"]

    def test_types_endpoint(self, client: TestClient) -> None:
        types = client.get("/api/v1/events/types").json()["types"]
        assert "conversation.created" in types
        assert "pipeline.completed" in types
