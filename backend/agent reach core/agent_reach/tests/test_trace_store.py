"""Tests for M9.3 — PipelineTraceStore and runtime observability.

Covers:
- PipelineTraceStore unit behavior (record / get / list / evict /
  aggregates / clear)
- IntelligentPipeline integration: every process() call persists a
  trace retrievable by request_id
- Observatory API: /traces and /trace/{id} serve real persisted data
- Chat API: responses carry request_id + trace linking to observatory
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from composition import build_intelligent_pipeline
from config.settings import get_settings
from core.intelligent_pipeline import PipelineTrace
from core.trace_store import PipelineTraceStore


# ===========================================================================
# Unit: PipelineTraceStore
# ===========================================================================


def _make_trace(**overrides) -> PipelineTrace:
    trace = PipelineTrace()
    for key, value in overrides.items():
        setattr(trace, key, value)
    return trace


class TestPipelineTraceStore:
    def test_record_and_get(self) -> None:
        store = PipelineTraceStore()
        trace = _make_trace()
        store.record(trace)
        assert store.get(trace.request_id) is trace
        assert len(store) == 1

    def test_get_missing_returns_none(self) -> None:
        store = PipelineTraceStore()
        assert store.get("nope") is None

    def test_list_recent_newest_first(self) -> None:
        store = PipelineTraceStore()
        t1, t2, t3 = _make_trace(), _make_trace(), _make_trace()
        store.record(t1)
        store.record(t2)
        store.record(t3)
        recent = store.list_recent(limit=2)
        assert [t.request_id for t in recent] == [t3.request_id, t2.request_id]

    def test_eviction_when_full(self) -> None:
        store = PipelineTraceStore(max_traces=2)
        t1, t2, t3 = _make_trace(), _make_trace(), _make_trace()
        store.record(t1)
        store.record(t2)
        store.record(t3)
        assert len(store) == 2
        assert store.get(t1.request_id) is None
        assert store.get(t2.request_id) is t2
        assert store.get(t3.request_id) is t3

    def test_re_record_moves_to_end(self) -> None:
        store = PipelineTraceStore(max_traces=2)
        t1, t2, t3 = _make_trace(), _make_trace(), _make_trace()
        store.record(t1)
        store.record(t2)
        store.record(t1)  # refresh t1 → t2 becomes oldest
        store.record(t3)
        assert store.get(t2.request_id) is None
        assert store.get(t1.request_id) is t1

    def test_invalid_max_traces_rejected(self) -> None:
        with pytest.raises(ValueError):
            PipelineTraceStore(max_traces=0)

    def test_clear(self) -> None:
        store = PipelineTraceStore()
        store.record(_make_trace())
        store.clear()
        assert len(store) == 0
        assert store.list_recent() == []

    def test_aggregates_empty_store_honest_zeros(self) -> None:
        store = PipelineTraceStore()
        agg = store.aggregates()
        assert agg["total_traces"] == 0
        assert agg["error_count"] == 0
        assert agg["error_rate"] == 0.0
        assert agg["avg_latency_ms"] == 0.0
        assert agg["stage_activity"] == {}

    def test_aggregates_computed_from_real_traces(self) -> None:
        store = PipelineTraceStore()
        store.record(
            _make_trace(
                total_latency_ms=100.0,
                memory_active=True,
                memory_items_retrieved=3,
                kg_active=True,
                kg_nodes_added=2,
                kg_edges_added=1,
            )
        )
        store.record(
            _make_trace(total_latency_ms=300.0, errors=["memory: boom"])
        )
        agg = store.aggregates()
        assert agg["total_traces"] == 2
        assert agg["error_count"] == 1
        assert agg["error_rate"] == 0.5
        assert agg["avg_latency_ms"] == 200.0
        assert agg["max_latency_ms"] == 300.0
        assert agg["stage_activity"]["memory"] == 1
        assert agg["stage_activity"]["knowledge_graph"] == 1
        assert agg["memory_items_retrieved"] == 3
        assert agg["kg_nodes_added"] == 2
        assert agg["kg_edges_added"] == 1

    def test_percentiles_ordered(self) -> None:
        store = PipelineTraceStore()
        for latency in (10.0, 20.0, 30.0, 40.0, 1000.0):
            store.record(_make_trace(total_latency_ms=latency))
        agg = store.aggregates()
        assert agg["p50_latency_ms"] <= agg["p95_latency_ms"] <= agg["max_latency_ms"]
        assert agg["max_latency_ms"] == 1000.0


# ===========================================================================
# Integration: pipeline persists traces
# ===========================================================================


@pytest.mark.asyncio
class TestPipelineTracePersistence:
    async def test_process_records_trace(self) -> None:
        pipeline = build_intelligent_pipeline()
        result = await pipeline.process("Research quantum computing")
        stored = pipeline.get_trace(result.trace.request_id)
        assert stored is result.trace
        assert len(pipeline.trace_store) == 1

    async def test_multiple_requests_all_traced(self) -> None:
        pipeline = build_intelligent_pipeline()
        r1 = await pipeline.process("First request")
        r2 = await pipeline.process("Second request")
        assert pipeline.get_trace(r1.trace.request_id) is not None
        assert pipeline.get_trace(r2.trace.request_id) is not None
        recent = pipeline.list_traces(limit=10)
        assert recent[0].request_id == r2.trace.request_id

    async def test_clear_also_clears_traces(self) -> None:
        pipeline = build_intelligent_pipeline()
        await pipeline.process("Something")
        pipeline.clear()
        assert len(pipeline.trace_store) == 0


# ===========================================================================
# API: observatory + chat expose persisted traces
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


class TestObservatoryTraceAPI:
    def test_chat_response_carries_request_id_and_trace(self, client: TestClient) -> None:
        resp = client.post("/api/v1/chat", json={"message": "Hello observability"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["request_id"]
        assert isinstance(data["trace"], dict)
        assert "total_latency_ms" in data["trace"]

    def test_trace_endpoint_returns_persisted_trace(self, client: TestClient) -> None:
        chat = client.post("/api/v1/chat", json={"message": "Trace me"}).json()
        request_id = chat["request_id"]
        resp = client.get(f"/api/v1/observatory/trace/{request_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["found"] is True
        assert body["trace"]["request_id"] == request_id

    def test_trace_endpoint_404_for_unknown_id(self, client: TestClient) -> None:
        resp = client.get("/api/v1/observatory/trace/does-not-exist")
        assert resp.status_code == 404

    def test_traces_listing_with_aggregates(self, client: TestClient) -> None:
        client.post("/api/v1/chat", json={"message": "One"})
        client.post("/api/v1/chat", json={"message": "Two"})
        resp = client.get("/api/v1/observatory/traces?limit=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] >= 2
        assert body["aggregates"]["total_traces"] >= 2
        assert body["aggregates"]["avg_latency_ms"] > 0
